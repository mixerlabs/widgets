{% comment %}
This renders javascript for interacting with widget ajax handlers via
post requests (using jquery)
{% endcomment %}

function {{ name }} () {
  $.ajax({
    type: "POST",
    url: "{{ ajaxurl }}",
    data: {{ args }},
    success: function ({{ variable }}) {
      {{ callback }}
    },
    error: function (request) {
        console.log(request.status)
      if (request.status == 403) {
        $.mixerbox("{% url login_dialog %}", "captcha_login", function(paa) {
          {% comment %}
             // The rest of the page won't show the user as logged in until a
             // reload, and the paa (post_auth_action) in the case of a new
             // account creation won't get displayed.
             // This is a lenghty ajax operation, so there is no great way of
             // doing that, other than reloading the page first and then doing
             // the ajax action, or using ajax to refresh all possible dom
             // nodes that are dependant on login status.
             // Maybe when all the widgets on a page leave edit mode,
             // then the page can reload and display the paa dialog?
          {% endcomment %}
          {{ name }}()
        })
      } else if (request.status == 409) {
        $.mixerbox("{% url captcha_dialog %}", "captcha_login", function(paa) {
          {% comment %}
             // paa may contain a url to open in a dialog that resends the
             // email valdiation code, not important if it interrupts flow
          {% endcomment %}
          {{ name }}()
        })
      }
    },
    dataType: "json"
  })
}

{{ name }}()

