// Sends a request for changesets from str (whitespace-separated)
// and includes the result into #changesets div.
function loadChangesets(str) {
    var url = window.server + '/changesets/' + str;
    var http = null;
    if (window.XMLHttpRequest) {
        http = new XMLHttpRequest();
    } else if (window.ActiveXObject) { // Older IE.
        http = new ActiveXObject("MSXML2.XMLHTTP.3.0");
    }
    http.onreadystatechange = function() {
        if( http.readyState != 4 || http.status != 200 ) return;
        document.getElementById('changesets').innerHTML = http.responseText;
    };
    http.open('GET', url, true);
    http.send(null);
}
