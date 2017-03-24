import logging

# flask
from flask import Flask, jsonify
import flask_cors

# Google
from google.cloud import datastore
from google.cloud.exceptions import ServiceUnavailable

# data
import numpy as np

RATING_KIND = 'Rating'

app = Flask(__name__)
flask_cors.CORS(app)
client = datastore.Client('cf-mr-service')

general_recommendation = []

@app.route('/')
def hello():
    return ''

@app.route('/movie/api/v1.0/recommendation', methods=['GET'])
def recommend_movies():
    movie_list = []
    for m in general_recommendation:
        movie_list.append({
            'movie_id': m[2]
            })

    return jsonify(movie_list)

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

    entity = retry_get_entity(client.key('Config', 'v1.0'))
    if entity is not None:
        user_rating_split_size = entity.get('user_rating_split_size', 0)

    query = client.query(kind=RATING_KIND)
    rating = list(query.fetch())
    user_rating = None
    for entity in rating:
        arr = np.fromstring(entity.get('data_str', ''), dtype=entity.get('dtype', 'uint8')).reshape(entity.get('rows', 1), entity.get('cols', 1))
        if user_rating is not None:
            user_rating = np.append(user_rating, arr, axis=0)
        else:
            user_rating = arr

    if user_rating is not None:
        log_info('Number of users = ' + str(user_rating.shape[0]) + ' | Number of movies = ' + str(user_rating.shape[1]))

    movie_ratings = [[0.0, 0, i] for i in xrange(user_rating.shape[1])]
    for movie_id in xrange(len(movie_ratings)):
        ratings = user_rating[:, movie_id:movie_id + 1]
        ratings = ratings[ratings.nonzero()]
        movie_ratings[movie_id][0] = ratings.mean()
        movie_ratings[movie_id][1] = ratings.shape[0]

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

load_data()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8081, debug=False)
