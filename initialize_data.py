import pandas
import numpy as np
from google.cloud import datastore
from math import floor
import pdb

RATING_KIND = 'Rating'
MOVIE_KIND = 'Movie'
PROJECT_ID = 'cf-mr-service'
client = datastore.Client(PROJECT_ID)

def load_from_store():
    query = client.query(kind=RATING_KIND)
    result = query.fetch()
    rating = list(result)
    read_rating = None
    for entity in rating:
        arr = np.fromstring(entity['data_str'], dtype=entity['dtype']).reshape(entity['rows'], entity['cols'])
        if read_rating is not None:
            read_rating = np.append(read_rating, arr, axis=0)
        else:
            read_rating = arr

def save_to_store():
    print 'save to store'
    header = ['user_id', 'item_id', 'rating', 'timestamp']
    rating_data = pandas.read_csv('u.data', sep='\t', names=header)

    n_users = rating_data.user_id.unique().shape[0]
    n_items = rating_data.item_id.unique().shape[0]
    print 'Number of users = ' + str(n_users) + ' | Number of movies = ' + str(n_items)

    user_rating = np.zeros((n_users, n_items), dtype='uint8')
    for line in rating_data.itertuples():
        user_rating[line[1] - 1, line[2] - 1] = line[3]

    # split_size = int(floor(1048487.0 * 3 / (4 * n_items)))
    split_size = int(floor(1048487.0 / n_items))

    entity_list = []
    print 'config split size = ' + str(split_size)
    config_key = key=client.key('Config', 'v1.0')
    entity = client.get(key=config_key)
    if entity is None:
        entity = datastore.Entity(key=config_key, exclude_from_indexes=['user_rating_split_size'])
    entity.update({
        'user_rating_split_size': split_size
        })
    entity_list.append(entity)

    for i in xrange(0, n_users + 1, split_size):
        print 'split rating data from ' + str(i) + ' to ' + str(i + split_size)
        entity = datastore.Entity(key=client.key(RATING_KIND, str(i / split_size)),
            exclude_from_indexes=['rows', 'cols', 'dtype', 'data_str'])
        sub_arr = user_rating[i : i + split_size]
        entity.update({
            'rows': sub_arr.shape[0],
            'cols': sub_arr.shape[1],
            'dtype': str(sub_arr.dtype),
            'data_str': sub_arr.tostring()
            })
        entity_list.append(entity)

    print 'prepare deleting indexed users'
    query = client.query(kind='User')
    query.keys_only()
    user_keys = []
    for user in query.fetch():
        print 'users to be delete ' + user.key.name 
        user_keys.append(user.key)

    with client.transaction():
        print 'run transaction'
        client.put_multi(entity_list)
        client.delete_multi(user_keys)

    entity_list = []
    print 'load movie info'
    f = open('u.item')
    while True:
        s = f.readline()
        if not s:
            break;
        item_info = s.split('|')
        entity = datastore.Entity(key=client.key(MOVIE_KIND, str(int(item_info[0]) - 1)),
            exclude_from_indexes=['title', 'imdb_url'])
        entity.update({
            'title': item_info[1],
            'imdb_url': item_info[4]
            })
        entity_list.append(entity)
        if (len(entity_list) >= 400):
            print 'put movie info'
            client.put_multi(entity_list)
            entity_list = []

    print 'initialization transaction'


if __name__ == '__main__':
    save_to_store()
    # load_from_store()
