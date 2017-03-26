import logging

# flask
from flask import Flask, jsonify, request
import flask_cors

# Google
from google.cloud import datastore
from google.cloud.exceptions import ServiceUnavailable
import google.auth.transport.requests
import google.oauth2.id_token

# data
import numpy as np
from sklearn.metrics.pairwise import pairwise_distances

RATING_KIND = 'Rating'
HTTP_REQUEST = google.auth.transport.requests.Request()

app = Flask(__name__)
flask_cors.CORS(app)
client = datastore.Client('cf-mr-service')

general_recommendation = []
user_rating = None
user_rating_split_size = 0
user_prediction = None

@app.route('/')
def hello():
    return ''

@app.route('/movie/api/v1.0/recommendation', methods=['GET'])
def recommend_movies():
    user_info = get_user_info()
    
    movie_list = []

    if user_info['index'] < 0:
        for m in general_recommendation:
            movie_list.append({
                'movie_id': m[2]
                })        
    elif user_info['index'] < user_rating.shape[0]:
        movies = []
        for i in xrange(user_rating.shape[1]):
            if user_rating[user_info['index']][i] == 0:
                movies.append((user_prediction[user_info['index']][i], i))

        movies.sort(reverse=True)        
        for m in movies:
            movie_list.append({
                'movie_id': m[1]
                })

    return jsonify(movie_list)

@app.route('/movie/api/v1.0/ratings', methods=['GET'])
def get_movie_rating():
    log_info('get movie ratings')
    user_info = get_user_info()
    if not user_info['email']:
        return 'Forbidden', 403

    ratings = []
    for i in user_rating[user_info['index']].nonzero()[0]:
        ratings.append({
          'movie_id': i,
          'rating': user_rating.item(user_info['index'], i)
        })
    return jsonify(ratings)

@app.route('/movie/api/v1.0/ratings/<int:movie_id>', methods=['PUT'])
def rate_movie(movie_id):
    log_info('rate movie')
    user_info = get_user_info()
    if not user_info['email']:
        return 'Forbidden', 403
    rating = -1
    if request.json:
        rating = request.json.get('rating', -1)
    if user_info['index'] < 0 or user_info['index'] >= user_rating.shape[0] \
        or movie_id < 0 or movie_id >= user_rating.shape[1] \
        or rating < 0 or rating > 5:
        return 'Invalid Parameter', 500
    user_rating[user_info['index']][movie_id] = rating
    predict_all()
    entity = setup_rating_entity(user_info['index'])
    client.put(entity)
    average_rating(movie_id)
    return jsonify({
        'movie_id': movie_id,
        'rating': rating
        })

@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500

def log_info(msg):
    print '[cfmr] ' + msg

def load_data():
    log_info('load data')

    global user_rating_split_size
    entity = retry_get_entity(client.key('Config', 'v1.0'))
    if entity is not None:
        user_rating_split_size = entity.get('user_rating_split_size', 0)

    global user_rating
    query = client.query(kind=RATING_KIND)
    rating = list(query.fetch())
    for entity in rating:
        arr = np.fromstring(entity.get('data_str', ''), dtype=entity.get('dtype', 'uint8')).reshape(entity.get('rows', 1), entity.get('cols', 1))
        if user_rating is not None:
            user_rating = np.append(user_rating, arr, axis=0)
        else:
            user_rating = arr

    if user_rating is not None:
        log_info('Number of users = ' + str(user_rating.shape[0]) + ' | Number of movies = ' + str(user_rating.shape[1]))

    predict_all()
    
    global movie_ratings
    movie_ratings = [[0.0, 0, i] for i in xrange(user_rating.shape[1])]
    for movie_id in xrange(len(movie_ratings)):
        average_rating(movie_id)

    global general_recommendation
    general_recommendation = sorted(movie_ratings, reverse=True)

# Seeing simlimar issue as reported on github
# https://github.com/GoogleCloudPlatform/google-cloud-python/issues/2896
# Adopt the temp solution first
def retry_get_entity(key):
    try:
        entity = client.get(key=key)
    except ServiceUnavailable:
        entity = client.get(key=key)
    return entity

def average_rating(movie_id):
    ratings = user_rating[:, movie_id:movie_id + 1]
    ratings = ratings[ratings.nonzero()]
    global movie_ratings
    movie_ratings[movie_id][0] = ratings.mean()
    movie_ratings[movie_id][1] = ratings.shape[0]

def predict_all():
    user_similarity = pairwise_distances(user_rating, metric='cosine')

    global user_prediction
    user_prediction = predict(user_rating, user_similarity)

def predict(ratings, similarity):
    mean_user_rating = ratings.mean(axis=1)
    #You use np.newaxis so that mean_user_rating has same format as ratings
    ratings_diff = (ratings - mean_user_rating[:, np.newaxis]) 
    return mean_user_rating[:, np.newaxis] + similarity.dot(ratings_diff) / np.array([np.abs(similarity).sum(axis=1)]).T

def get_user_info():
    id_token = request.headers['Authorization'].split(' ').pop()
    claims = None
    if id_token != 'null' and id_token != 'undefined':
        claims = google.oauth2.id_token.verify_firebase_token(id_token, HTTP_REQUEST)

    email = ''
    index = -1
    if claims is not None:
        email = claims['email']
        entity = retry_get_entity(client.key('User', email))
        if entity is not None:
            index = entity.get('user_index', -1)
        elif user_rating_split_size > 0:
            # authorized user without index, add to rating matrix and db
            global user_rating
            index = user_rating.shape[0]
            user_rating = np.append(user_rating, np.zeros((1, user_rating.shape[1]), dtype='uint8'), axis = 0)

            entity = setup_rating_entity(index)
            user_entity = datastore.Entity(key=client.key('User', email))
            user_entity['user_index'] = index
            try:
                with client.transaction():
                    client.put_multi([entity, user_entity])
            except:
                user_rating = np.delete(user_rating, user_info['index'], 0)
                index = -1
            else:
                predict_all()
    return {
        'email': email,
        'index': index
        }

def setup_rating_entity(user_index):
    data_set_index = user_index / user_rating_split_size
    key = client.key(RATING_KIND, str(data_set_index))
    entity = client.get(key=key)
    if entity is None:
        entity = datastore.Entity(key=key, exclude_from_indexes=['data_str'])
    save_start_index = data_set_index * user_rating_split_size
    sub_arr = user_rating[save_start_index : save_start_index + user_rating_split_size]
    entity['rows'] = sub_arr.shape[0]
    entity['cols'] = sub_arr.shape[1]
    entity['dtype'] = str(sub_arr.dtype)
    entity['data_str'] = sub_arr.tostring()
    return entity

load_data()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8081, debug=False)
