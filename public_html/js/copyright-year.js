/*
 * フッターのコピーライト年を現在の年にする。
 * HTML に書いてある年は、JavaScript が動かないときの表示。
 */
(function () {
  'use strict';

  var year = String(new Date().getFullYear());
  var els = document.querySelectorAll('.copyright-year');
  for (var i = 0; i < els.length; i++) {
    els[i].textContent = year;
  }
})();
