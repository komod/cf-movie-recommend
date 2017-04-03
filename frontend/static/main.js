$(function(){
  // Initialize Firebase
  var config = {
    apiKey: "AIzaSyDaolLo0xOVJq0SblMuG60dtct11_D2bKs",
    authDomain: "cf-mr-service.firebaseapp.com",
    databaseURL: "https://cf-mr-service.firebaseio.com",
    storageBucket: "gs://cf-mr-service.appspot.com/",
  };

  var userIdToken;

  // Firebase log-in
  function configureFirebaseLogin() {

    firebase.initializeApp(config);

    // [START onAuthStateChanged]
    firebase.auth().onAuthStateChanged(function(user) {
      if (user) {
        var name = user.displayName;
        var welcomeName = name ? name : user.email;

        user.getToken().then(function(idToken) {
          userIdToken = idToken;
          getRatedMovie();
          getMovieRecommendations();

          $('#user').text(welcomeName);
        });
        $('.logged-out').hide();
        $('.logged-in').show();
      } else {
        userIdToken = null;
        getMovieRecommendations();
        $('.logged-in').hide();
        $('.logged-out').show();
      }
    // [END onAuthStateChanged]

    });

  }

  // [START configureFirebaseLoginWidget]
  // Firebase log-in widget
  function configureFirebaseLoginWidget() {
    var uiConfig = {
      'signInSuccessUrl': '/',
      'signInOptions': [
        // Leave the lines as is for the providers you want to offer your users.
        firebase.auth.GoogleAuthProvider.PROVIDER_ID,
        firebase.auth.EmailAuthProvider.PROVIDER_ID
      ],
    };

    var ui = new firebaseui.auth.AuthUI(firebase.auth());
    ui.start('#firebaseui-auth-container', uiConfig);
  }
  // [END configureFirebaseLoginWidget]

  var backendHostUrl = 'http://backend-dot-cf-mr-service.appspot.com';
  // var backendHostUrl = 'http://localhost:8081';

  var MOVIE_ID_PREFIX = 'movie-';
  var isGettingRecommendation = false;
  var lastRecommendingTime = 0

  function getMovieRecommendations() {
    if (isGettingRecommendation) {
      return $.when();
    }
    isGettingRecommendation = true;
    return $.ajax(backendHostUrl + '/movie/api/v1.0/recommendation', {
      /* Set header for the XMLHttpRequest to get data from the web server
      associated with userIdToken */
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      }
    }).then(function(data){
      $('#recommend-movies').empty();
      var defs = [];
      data.movie_list.forEach(function(movie){
        if ($('#' + MOVIE_ID_PREFIX + movie.movie_id).length == 0) {
          defs.push(addMovieItem(movie, 'recommend-movies'));
        }
      });
      lastRecommendingTime = parseServerIsoTime(data.up_to_date_time);
      return $.when.apply($, defs);
    }).always(function() {
      isGettingRecommendation = false;
    });
  }

  function parseServerIsoTime(s) {
    if (s.length > 4) {
      return Date.parse(s.substring(0, s.length - 4) + 'Z');
    } else {
      return 0;
    }
  }

  var ratings = {};

  function getRatedMovie() {
    $.ajax(backendHostUrl + '/movie/api/v1.0/ratings', {
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      },
    }).then(function(data){
      ratings = {}
      $('#rated-movies').empty();
      data.forEach(function(movie){
        ratings[movie.movie_id] = movie.rating;
        addMovieItem(movie, 'rated-movies');
      });
    });
  }

  function rateMovie(movie_id, rating_str) {
    if (isNaN(movie_id) || parseInt(movie_id) < 0)
      return;
    rating = parseInt(rating_str, 10);

    var detached_element = null;
    if (rating > 0 && typeof(ratings[movie_id]) === 'undefined') {
      $('#rated-movies').append($('#' + MOVIE_ID_PREFIX + movie_id));
    } else if (rating == 0) {
      detached_element = $('#' + MOVIE_ID_PREFIX + movie_id).detach();
    }
    $.ajax(backendHostUrl + '/movie/api/v1.0/ratings/' + movie_id, {
      type: 'PUT',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      },
      data: JSON.stringify({
        'rating': rating
      })
    }).then(function(data) {
      if (data.rating > 0) {
        ratings[data.movie_id] = data.rating
      } else {
        delete ratings[data.movie_id];
        $('#' + MOVIE_ID_PREFIX + data.movie_id).remove();
      }
    }, function(data) {
      console.log('rate movie failed');
      if (ratings[movie_id] > 0) {
        if (detached_element != null) {
          $('#rated-movies').append(detached_element);
          detached_element = null;
        }
        $('#' + MOVIE_ID_PREFIX + movie_id + ' select').val(ratings[movie_id]);
      } else {
        $('#' + MOVIE_ID_PREFIX + movie_id).remove();
      }
    });
  }

  var genres = ['unknown', 'Action', 'Adventure', 'Animation', 'Children\'s',
    'Comedy', 'Crime', 'Documentary', 'Drama', 'Fantasy', 'Film-Noir', 'Horror',
    'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Thriller', 'War', 'Western'
  ]

  function addMovieItem(movie, parent_id) {
    $('<div>').attr('id', MOVIE_ID_PREFIX + movie.movie_id).addClass('movie-item').appendTo($('#' + parent_id));
    return $.ajax(backendHostUrl + '/movie/api/v1.0/info/' + movie.movie_id).then(function(movie_info){
      a = $('<a>').attr('href', movie_info.imdb_url).attr('target', '_blank');
      if (movie_info.imdb_poster_image_url) {
        a.append($('<img>').attr('src', movie_info.imdb_poster_image_url).addClass('center-block'));
      } else {
        a.append($('<span>').text(movie_info.title).addClass('poster-like center-block'));
      }
      m = $('#' + MOVIE_ID_PREFIX + movie.movie_id).append(a);
      if (userIdToken != null) {
        e = $('<select>').append($('<option>').text('None').val(0));
        for(var i = 1; i <=5; ++i)
          e.append($('<option>').text(i))
        if (movie.rating > 0)
          e.val(movie.rating);
        e.change(function(event) {
          rateMovie(this.parentNode.parentNode.id.split(MOVIE_ID_PREFIX)[1], this.value);
        });
        m.append($('<div>').append(e));

        genre_string = ''
        mask = movie_info.genre.split('|')
        for (var i = 0; i < movie_info.genre.length && i < genres.length; ++i) {
          if (mask[i] > 0) {
            if (genre_string.length > 0) {
              genre_string = genre_string.concat(' ');
            }
            genre_string = genre_string.concat(genres[i]);
          }
        }
        m.append(
          $('<div>').append(
            $('<label>').text('Rating:')).append(
            $('<span>').text(movie_info.average_rating.toFixed(1) + ' / ' + movie_info.rating_count))).append(
          $('<div>').append(
            $('<label>').text('Genre:')).append(
            $('<span>').text(genre_string).attr('data-toggle', 'tooltip').attr('title', genre_string).addClass('hiding-text'))
        );
        if (typeof(movie.score) !== 'undefined') {
          m.append($('<div>').append($('<label>').text('Score')).append($('<span>').text(movie.score.toFixed(2))).addClass('score'));
        }
      }
    });
  }
  // [START signOutBtn]
  // Sign out a user
  var signOutBtn =$('#sign-out');
  signOutBtn.click(function(event) {
    event.preventDefault();

    firebase.auth().signOut().then(function() {
      console.log("Sign out successful");
    }, function(error) {
      console.log(error);
    });
  });
  // [END signOutBtn]

  configureFirebaseLogin();
  configureFirebaseLoginWidget();

  function updateMovieRecommendations() {
    return $.ajax(backendHostUrl + '/movie/api/v1.0/recommendation/uptodate').then(function(time){
      if (lastRecommendingTime < parseServerIsoTime(time)) {
        return getMovieRecommendations();
      }
    }).always(function() {
      setTimeout(updateMovieRecommendations, 6000);
    });
  }
  setTimeout(updateMovieRecommendations, 6000);
});
