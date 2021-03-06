import logging
import traceback
import threading
import time
import datetime
import requests

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
import bs4

# local development
# import pdb
# import pandas

RATING_KIND = 'Rating'
MOVIE_KIND = 'Movie'
POSTER_URL_NAME = 'imdb_poster_image_url'
HTTP_REQUEST = google.auth.transport.requests.Request()

app = Flask(__name__)
flask_cors.CORS(app)
client = datastore.Client('cf-mr-service')

general_recommendation = []
user_rating = None
user_rating_split_size = 0
movies_to_update = set()
users_to_update = set()
movie_info_to_update = set()
rating_data_lock = threading.Lock()
user_prediction = None
modeling_time = datetime.datetime.utcnow().isoformat() + 'Z'
movie_info = []
all_user_info = {}

@app.route('/')
def hello():
    return ''

@app.route('/movie/api/v1.0/recommendation', methods=['GET'])
def recommend_movies():
    log_info('recommand movies')
    user_info = get_user_info()
    
    movie_list = []

    if user_info['index'] < 0:
        for m in general_recommendation:
            movie_list.append({
                'movie_id': m[2],
                'score': m[0]
                })        
            if len(movie_list) >= 20:
                break
    elif user_info['index'] < user_rating.shape[0]:
        movies = []
        rating_data_lock.acquire()
        for i in xrange(user_rating.shape[1]):
            if user_rating[user_info['index']][i] == 0:
                movies.append((user_prediction[user_info['index']][i], i))
        rating_data_lock.release()

        movies.sort(reverse=True)        
        for m in movies:
            movie_list.append({
                'movie_id': m[1],
                'score': m[0]
                })
            if len(movie_list) >= 20:
                break

    return jsonify({
        'movie_list': movie_list,
        'up_to_date_time': modeling_time
        })

@app.route('/movie/api/v1.0/recommendation/uptodate', methods=['GET'])
def get_modeling_time():
    return modeling_time

@app.route('/movie/api/v1.0/ratings', methods=['GET'])
def get_movie_rating():
    log_info('get movie ratings')
    user_info = get_user_info()
    if not user_info['email']:
        return 'Forbidden', 403

    ratings = []
    rating_data_lock.acquire()
    non_zero_ratings = user_rating[user_info['index']].nonzero()[0]
    rating_data_lock.release()
    for i in non_zero_ratings:
        ratings.append({
          'movie_id': i,
          'rating': user_rating.item(user_info['index'], i)
        })
    return jsonify(ratings)

@app.route('/movie/api/v1.0/ratings/<int:movie_id>', methods=['PUT'])
def rate_movie(movie_id):
    log_info('rate movie ' + str(movie_id))
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
    rating_data_lock.acquire()
    user_rating[user_info['index']][movie_id] = rating
    users_to_update.add(user_info['index'])
    movies_to_update.add(movie_id)
    rating_data_lock.release()

    return jsonify({
        'movie_id': movie_id,
        'rating': rating
        })

@app.route('/movie/api/v1.0/info/<int:movie_id>', methods=['GET'])
def get_movie_info(movie_id):
    info = movie_info[movie_id]
    if not info:
        return
    if POSTER_URL_NAME not in info:
        info[POSTER_URL_NAME] = get_poster_url(movie_id)
    return jsonify({
        'movie_id': movie_id,
        'title': info.get('title', ''),
        'imdb_url': info.get('imdb_url', ''),
        POSTER_URL_NAME: info.get(POSTER_URL_NAME, ''),
        'genre': info.get('genre', ''),
        'average_rating': movie_ratings[movie_id][0],
        'rating_count': movie_ratings[movie_id][1]
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
        log_info('split size = ' + str(user_rating_split_size))

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

    global all_user_info
    query = client.query(kind='User')
    for user in query.fetch():
        user_index = user.get('user_index', -1)
        if user_index >= 0:
         all_user_info[user.key.name] = user_index

    load_movie_info_from_file()

def load_movie_info_from_file():
    global movie_info
    with open('u.item', 'r') as f:
        for line in f:
            item_info = line[:-1].split('|', 5)
            movie_info.append({
                'title': item_info[1],
                'imdb_url': item_info[4],
                'genre': item_info[5]
                })

def initialize():
    load_data()
    # load_local_data()
  
    predict_all()
    
    global movie_ratings
    movie_ratings = [[0.0, 0, i] for i in xrange(user_rating.shape[1])]
    for movie_id in xrange(len(movie_ratings)):
        average_rating(movie_id)

    global general_recommendation
    general_recommendation = sorted(movie_ratings, reverse=True)

    for i in xrange(20):
        movie_id = general_recommendation[i][2]
        movie_info[movie_id][POSTER_URL_NAME] = get_poster_url(movie_id)

    t = threading.Thread(target=daemon_task)
    t.setDaemon(True)
    t.start()

def get_or_create_entity(key):
    entity = retry_get_entity(key)
    if entity is None:
        entity = datastore.Entity(key=key)
    return entity

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
    rating_data_lock.acquire()
    ratings = user_rating[:, movie_id:movie_id + 1]
    ratings = ratings[ratings.nonzero()]
    rating_data_lock.release()
    global movie_ratings
    movie_ratings[movie_id][0] = ratings.mean()
    movie_ratings[movie_id][1] = ratings.shape[0]

def predict_all():
    rating_data_lock.acquire()
    user_similarity = pairwise_distances(user_rating, metric='cosine')

    global user_prediction
    user_prediction = predict(user_rating, user_similarity)
    rating_data_lock.release()

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
        index = all_user_info.get(email, -1)
        if index < 0:
            entity = retry_get_entity(client.key('User', email))
            if entity is None:
                entity = datastore.Entity(key=client.key('User', email))
            else:
                index = entity.get('user_index', -1)
        if index < 0 and user_rating_split_size > 0:
            # authorized user without index, add to rating matrix and db
            global user_rating
            rating_data_lock.acquire()
            index = user_rating.shape[0]
            user_rating = np.append(user_rating, np.zeros((1, user_rating.shape[1]), dtype='uint8'), axis = 0)
            log_info('append new user to rating data, current size = ' + str(user_rating.shape[0]))
            rating_data_lock.release()

            entity = setup_rating_entity(index)
            user_entity = datastore.Entity(key=client.key('User', email))
            user_entity['user_index'] = index
            try:
                with client.transaction():
                    client.put_multi([entity, user_entity])
            except:
                rating_data_lock.acquire()
                user_rating = np.delete(user_rating, user_info['index'], 0)
                rating_data_lock.release()
                index = -1
                log_info('exception caught, restore rating data to size = ' + str(user_rating.shape[0]))
            else:
                predict_all()
                global modeling_time
                modeling_time = datetime.datetime.utcnow().isoformat() + 'Z'
    log_info('user ' + str(index) + ' : ' + email)
    return {
        'email': email,
        'index': index
        }

def setup_rating_entity(user_index):
    data_set_index = user_index / user_rating_split_size
    entity = retry_get_entity(client.key(RATING_KIND, str(data_set_index)))
    if entity is None:
        entity = datastore.Entity(key=key, exclude_from_indexes=['data_str'])
    save_start_index = data_set_index * user_rating_split_size
    rating_data_lock.acquire()
    sub_arr = user_rating[save_start_index : save_start_index + user_rating_split_size]
    entity['rows'] = sub_arr.shape[0]
    entity['cols'] = sub_arr.shape[1]
    entity['dtype'] = str(sub_arr.dtype)
    entity['data_str'] = sub_arr.tostring()
    rating_data_lock.release()
    return entity

def get_poster_url(movie_id):
    poster_url = ''
    entity = retry_get_entity(client.key(MOVIE_KIND, str(movie_id)))
    if entity is not None:
        poster_url = entity.get(POSTER_URL_NAME, '')
    else:
        url = movie_info[movie_id].get('imdb_url', '')
        resp = requests.get(url)
        if resp.status_code == requests.codes.ok:
            soup = bs4.BeautifulSoup(resp.content, 'html.parser')
            ps = soup.find('div', attrs={'class': 'poster'})
            if ps is not None:
                poster_url = ps.img.get('src', '')
            movie_info[movie_id][POSTER_URL_NAME] = poster_url
            if poster_url:
                movie_info_to_update.add(movie_id)
    return poster_url

def daemon_task():
    global new_ratings
    while True:
        try:
            rating_data_lock.acquire()
            update_list = sorted(movies_to_update)
            movies_to_update.clear()
            rating_data_lock.release()
            if update_list:
                predict_all()
                for i in update_list:
                    average_rating(i)
                global modeling_time
                modeling_time = datetime.datetime.utcnow().isoformat() + 'Z'
   
            entity_list = []

            rating_data_lock.acquire()
            update_list = sorted(users_to_update)
            users_to_update.clear()
            rating_data_lock.release()
            if update_list:
                log_info('update user ' + str(update_list))
                i = 0
                while i < len(update_list):
                    entity_list.append(setup_rating_entity(update_list[i]))
                    next_base = (update_list[i] / user_rating_split_size + 1) * user_rating_split_size
                    while i < len(update_list) and update_list[i] < next_base:
                        i += 1

            update_list = sorted(movie_info_to_update)
            movie_info_to_update.clear()
            for i in update_list:
                if POSTER_URL_NAME in movie_info[i]:
                    entity = get_or_create_entity(client.key(MOVIE_KIND, str(i)))
                    entity.update({
                        POSTER_URL_NAME: movie_info[i][POSTER_URL_NAME]
                    })
                    entity_list.append(entity)

            if entity_list:
                client.put_multi(entity_list)
                log_info('synced to datastore');
        except Exception:
            log_info('exception caught')
            traceback.print_exc() 
        time.sleep(3)

def load_local_data():
    log_info('load local data')

    global user_rating_split_size
    user_rating_split_size = 623

    header = ['user_id', 'item_id', 'rating', 'timestamp']
    rating_data = pandas.read_csv('r.data', sep='\t', names=header)

    n_users = rating_data.user_id.unique().shape[0]
    n_items = rating_data.item_id.unique().shape[0]
    print 'Number of users = ' + str(n_users) + ' | Number of movies = ' + str(n_items)

    global user_rating
    user_rating = np.zeros((n_users, n_items), dtype='uint8')
    for line in rating_data.itertuples():
        user_rating[line[1] - 1, line[2] - 1] = line[3]

    load_movie_info_from_file()

initialize()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8081, debug=False)
