# cf-movie-recommend

This project tends to implement a simple CF(Collaborative Filtering)-based movie recommendation service. The service is deployed to Google Cloud Platform and includes two running instances which use different environments.

The recommendation uses the Memory-Based Collaborative Filtering introduced in this tutorial https://online.cambridgecoding.com/notebooks/eWReNYcAfB/implementing-your-own-recommender-systems-in-python-2 with the same initial dataset ml-100k from MovieLens.

The user registration and login function are integrated with Firebase. So it can be easily extended to include more sign-in identity with Facebook, Twitter and GitHub.

The "default" service (frontend folder) renders a simple single page and interact with the "backend" service through RESTful web API. The "backend" service uses Flask and exports the API to provide the rating and recommending functions. The MovieLens dataset is saved to Google Cloud Datastore prior to the instance start up with the utility code (initialize_data.py), and then the service tried to maintain the consistency between Datastore and in-place variables.

TODO:

- Concurrent users handling
- Frontend beautify and behavior refinement
- Adopt larger initial dataset

