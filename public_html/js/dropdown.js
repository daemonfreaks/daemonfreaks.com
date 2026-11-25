/*
 * ナビゲーションのドロップダウンメニュー。
 * Bootstrap 3.3.4 の dropdown.js と同じ動作を、ライブラリなしで再現している。
 *
 *   - [data-toggle="dropdown"] をクリックすると、親要素の open クラスを付け外しする
 *   - メニューの外をクリックすると閉じる
 *   - トグルにフォーカスがあるとき、↑ ↓ Space で開き、Esc で閉じる
 */
(function () {
  'use strict';

  var TOGGLE = '[data-toggle="dropdown"]';

  function closeAll(event) {
    if (event && event.button === 2) return; // 右クリックでは閉じない
    var toggles = document.querySelectorAll(TOGGLE);
    for (var i = 0; i < toggles.length; i++) {
      var parent = toggles[i].parentNode;
      if (!parent.classList.contains('open')) continue;
      // メニュー内の入力欄をクリックしたときは閉じない
      if (event && event.type === 'click' &&
          /^(INPUT|TEXTAREA)$/.test(event.target.tagName) &&
          parent.contains(event.target)) continue;
      toggles[i].setAttribute('aria-expanded', 'false');
      parent.classList.remove('open');
    }
  }

  function toggle(el) {
    var parent = el.parentNode;
    var wasOpen = parent.classList.contains('open');
    closeAll();
    if (!wasOpen) {
      el.focus();
      el.setAttribute('aria-expanded', 'true');
      parent.classList.add('open');
    }
  }

  document.addEventListener('click', function (event) {
    var el = event.target.closest ? event.target.closest(TOGGLE) : null;
    if (el) {
      event.preventDefault();
      toggle(el);
    } else {
      closeAll(event);
    }
  });

  document.addEventListener('keydown', function (event) {
    var key = event.keyCode;
    if (key !== 38 && key !== 40 && key !== 27 && key !== 32) return;
    if (/^(INPUT|TEXTAREA)$/.test(event.target.tagName)) return;

    // トグルにフォーカスがあるときだけ処理する（メニュー内のキー操作はブラウザ標準のまま）
    var el = event.target.closest(TOGGLE);
    if (!el) return;

    event.preventDefault();
    event.stopPropagation();

    var isOpen = el.parentNode.classList.contains('open');
    if (!isOpen && key !== 27) {
      toggle(el);
    } else if (isOpen && key === 27) {
      el.focus();
      toggle(el);
    }
  });
})();
