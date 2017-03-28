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
        $('#logged-out').hide();
        $('#logged-in').show();
      } else {
        userIdToken = null;
        getMovieRecommendations();
        $('#logged-in').hide();
        $('#logged-out').show();
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

  function getMovieRecommendations() {
    if (isGettingRecommendation) {
      return;
    }
    isGettingRecommendation = true;
    $.ajax(backendHostUrl + '/movie/api/v1.0/recommendation', {
      /* Set header for the XMLHttpRequest to get data from the web server
      associated with userIdToken */
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      }
    }).then(function(data){
      $('#recommend-movies').empty();
      var defs = [];
      data.forEach(function(movie){
        id = MOVIE_ID_PREFIX + movie.movie_id;
        if ($('#' + id).length == 0) {
          $('<div>').attr('id', id).appendTo($('#recommend-movies'));
          defs.push(setupMovieItem(movie));
        }
      });
      return $.when.apply($, defs);
    }).always(function() {
      isGettingRecommendation = false;
    });
  }

  function getRatedMovie() {
    $.ajax(backendHostUrl + '/movie/api/v1.0/ratings', {
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      },
    }).then(function(data){
      $('#rated-movies').empty();
      data.forEach(function(movie){
        $('<div>').attr('id', MOVIE_ID_PREFIX + movie.movie_id).appendTo($('#rated-movies'));
        setupMovieItem(movie);
      });
    });
  }

  function rateMovie(movie_id, rating_str) {
    if (isNaN(movie_id) || parseInt(movie_id) < 0)
      return;
    rating = parseInt(rating_str, 10);
    $.ajax(backendHostUrl + '/movie/api/v1.0/ratings/' + movie_id, {
      type: 'PUT',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + userIdToken
      },
      data: JSON.stringify({
        'rating': rating
      })
    }).then(function(data){
      getRatedMovie();
      getMovieRecommendations();
    });
  }

  function setupMovieItem(movie) {
    return $.ajax(backendHostUrl + '/movie/api/v1.0/info/' + movie.movie_id).then(function(movie_info){
      $('#' + MOVIE_ID_PREFIX + movie_info.movie_id).append($('<a>').text(movie_info.title).attr('href', movie_info.imdb_url).attr('target', '_blank'))
      if (userIdToken != null) {
        e = $('<select>').append($('<option>').text('None').val(0));
        for(var i = 1; i <=5; ++i)
          e.append($('<option>').text(i))
        if (movie.rating > 0)
          e.val(movie.rating);
        e.change(function(event) {
          rateMovie(this.parentNode.id.split(MOVIE_ID_PREFIX)[1], this.value);
        });
        $('#' + MOVIE_ID_PREFIX + movie_info.movie_id).append(e);
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

});
