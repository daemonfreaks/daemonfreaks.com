/*
 * トップページの Recent Activities。
 * サーバー側の tools/fetch_activities.py が定期的に書き出す activities.json を読み、
 * 「サービス名 - タイトル [yyyy/mm/dd hh:mm]」の一覧を作る。
 *
 * セクションは HTML では hidden にしてある。1 件以上表示できたときだけ見せる。
 * JSON が読めないときや 0 件のときは、見出しごと隠したままにする。
 */
(function () {
  'use strict';

  var JSON_URL = 'activities.json';
  var HTTP_URL = /^https?:\/\//;

  var section = document.getElementById('recent-activities');
  var list = document.getElementById('feed');
  if (!section || !list || !window.fetch) return;

  function pad(n) {
    return ('0' + n).slice(-2);
  }

  // 閲覧者のローカル時刻で yyyy/mm/dd hh:mm にする。
  function formatDate(date) {
    return date.getFullYear() + '/' + pad(date.getMonth() + 1) + '/' + pad(date.getDate()) +
           ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function externalLink(text, url) {
    var a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = text;
    return a;
  }

  // 表示できない項目（リンクが http(s) でない、日時が読めないなど）は null を返す。
  function buildItem(item) {
    if (!item || typeof item.title !== 'string' || !item.title) return null;
    if (typeof item.source !== 'string' || !item.source) return null;
    if (typeof item.url !== 'string' || !HTTP_URL.test(item.url)) return null;
    var date = new Date(item.published);
    if (isNaN(date.getTime())) return null;

    var li = document.createElement('li');
    if (typeof item.source_url === 'string' && HTTP_URL.test(item.source_url)) {
      li.appendChild(externalLink(item.source, item.source_url));
    } else {
      li.appendChild(document.createTextNode(item.source));
    }
    li.appendChild(document.createTextNode(' - '));
    li.appendChild(externalLink(item.title, item.url));
    li.appendChild(document.createTextNode(' '));
    var small = document.createElement('small');
    small.textContent = '[' + formatDate(date) + ']';
    li.appendChild(small);
    return li;
  }

  fetch(JSON_URL, { cache: 'no-cache' })
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(function (data) {
      var items = data && data.items;
      if (!Array.isArray(items)) return;
      var fragment = document.createDocumentFragment();
      var count = 0;
      for (var i = 0; i < items.length; i++) {
        var li = buildItem(items[i]);
        if (li) {
          fragment.appendChild(li);
          count++;
        }
      }
      if (count === 0) return;
      list.textContent = '';
      list.appendChild(fragment);
      section.hidden = false;
    })
    .catch(function () {
      // 読めなければ隠したままにする。
    });
})();
