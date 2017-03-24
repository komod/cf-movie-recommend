$(function(){
  // Initialize Firebase
  var config = {
    apiKey: "AIzaSyDaolLo0xOVJq0SblMuG60dtct11_D2bKs",
    authDomain: "cf-mr-service.firebaseapp.com",
    databaseURL: "https://cf-mr-service.firebaseio.com",
    storageBucket: "gs://cf-mr-service.appspot.com/",
  };

  // Firebase log-in
  function configureFirebaseLogin() {

    firebase.initializeApp(config);

    // [START onAuthStateChanged]
    firebase.auth().onAuthStateChanged(function(user) {
      if (user) {
        $('#logged-out').hide();
        $('#logged-in').show();
      } else {
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
  function getMovieRecommendations() {
    $.ajax(backendHostUrl + '/movie/api/v1.0/recommendation').then(function(data){
      $('#recommend-movies').empty();
      data.forEach(function(movie){
        $('#recommend-movies').append($('<p>').text(movie.movie_id));
      });
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
