/*
Copyright (C) 2010 Pierre St Juste <ptony82@ufl.edu>, University of Florida

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
*/

var prevState = "";
var gquery = "";
var del = "";

$(document).ready(init);

function init() {
  document.title = "Litter - Twitter for the LAN";
  loadPage();
  loadHeader();
  loadSearch();
  getState();
  //window.setInterval(getState, 15000);
}

function loadPage() {
  $("<div/>", {'id' : 'wrapper'}).appendTo("body");
  $("<div/>", {'id' : 'header'}).appendTo("#wrapper");
  $("<div/>", {'id' : 'subheader'}).appendTo("#header");
  $("<div/>", {'id' : 'maindiv'}).appendTo("#wrapper");
  $("<div/>", {'id' : 'searchdiv'}).appendTo("#maindiv");
  $("<div/>", {'id' : 'inputdiv'}).appendTo("#maindiv");
  $("<div/>", {'id' : 'resultsdiv'}).appendTo("#maindiv");
}

function loadHeader() {
  $("<h1/>", {text : 'Litter - Twitter for the LAN'}).appendTo("#subheader");
  var menu = $("<ul/>").appendTo("#subheader");
  menu.append($("<li/>", {text : 'Refresh', click : doNothing}));
}

function doNothing() {}

function loadSearch() {
  $("<input/>", {"name" : "search"}).appendTo("#searchdiv");

  var msg = "Post";
  $("<button/>", {text : msg, click : doSearch}).appendTo("#searchdiv");

}

function loadResults(state) {
  $("#resultsdiv").text("");
  createTable();

  for (var i = 0; i < state.length; i++) {
    addResult(state[i]);
  }

}

function createTable() {
  var table = $("<table/>").appendTo("#resultsdiv");
  var row = $("<tr/>").appendTo(table);

  var imgcol = $("<td/>");
  var title = "";
  var infocol = $("<td/>", { text: title, 'width' : '100%', 
    'class' : 'table_title'});
  var ratingcol = $("<td/>");
  imgcol.appendTo(row);
  infocol.appendTo(row);
  ratingcol.appendTo(row);
}

function addResult(result) {
  var row = $("<tr/>").appendTo("#resultsdiv table");
  var imgcol = $("<td/>");
  var infocol = $("<td/>", { 'width': '100%'});
  var ratingcol = $("<td/>");
  imgcol.appendTo(row);
  infocol.appendTo(row);
  ratingcol.appendTo(row);

  img_src = "http://gravatar.com/avatar/?d=mm"
  $("<img/>", {'src' : img_src, 'width' : '40px', 
    'height' : '40px'}).appendTo(imgcol);

  infocol.append($("<p/>", {text: result.uid, 'class' : 'name',
    'id' : result.uid, click : doNothing}));

  infocol.append($("<p/>", { text: result.msg, 'class' : 'info'}));

  ratingcol.append($("<span/>", {text: '','class': 'rating'}));

  $("body").data(result.uid, result);
}

function clearInput() {
  $("#inputdiv").dialog("close");
  $("#inputdiv").text("");
}

function getState() {
  $.ajax({type: "POST", url: "/api", dataType: 'json', 
    data : "json={\"m\": \"get_posts\"}", success: processState});
}


function doSearch() {
  var method = "sdns.search";
  var query = encodeURIComponent($(":input[name=search]").val());
  gquery = query;
  $.ajax({type: "POST", url: "state.xml", data : "m=" + method + 
    "&q=" + query, success: loadResults});
  clearInput();
}

function processState(state) {
  loadResults(state);
}
