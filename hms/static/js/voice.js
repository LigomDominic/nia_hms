/* Voice-to-text for any input/textarea marked with data-voice (Web Speech API). */
(function () {
  var cfg = window.HMS_VOICE || {};
  if (cfg.enabled === false) return;
  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var fields = document.querySelectorAll('[data-voice]');
  if (!fields.length) return;

  var SPOKEN = [
    [/\s*\b(full stop|period)\b/gi, '.'], [/\s*\bcomma\b/gi, ','],
    [/\s*\bquestion mark\b/gi, '?'], [/\s*\bcolon\b/gi, ':'],
    [/\s*\b(new line|next line)\b\s*/gi, '\n'], [/\s*\bnew paragraph\b\s*/gi, '\n\n']
  ];
  function tidy(text) {
    if (cfg.punctuation !== false) SPOKEN.forEach(function (r) { text = text.replace(r[0], r[1]); });
    return text;
  }
  function capitalise(prev, text) {
    if (!prev.trim() || /[.?!\n]\s*$/.test(prev)) return text.charAt(0).toUpperCase() + text.slice(1);
    return text;
  }

  var active = null;  // {rec, field, btn, base}

  function stop() {
    if (!active) return;
    try { active.rec.stop(); } catch (e) {}
  }

  function start(field, btn, status) {
    if (active) { var same = active.field === field; stop(); if (same) return; }
    var rec = new Recognition();
    rec.lang = cfg.lang || 'en-NG';
    rec.continuous = true;
    rec.interimResults = true;
    var state = { rec: rec, field: field, btn: btn, base: field.value };
    active = state;

    rec.onstart = function () {
      btn.classList.add('recording'); btn.setAttribute('aria-pressed', 'true');
      btn.title = 'Stop dictation'; status.textContent = 'Listening… speak now. Click the mic again to stop.';
      status.className = 'voice-status on';
    };
    rec.onresult = function (event) {
      var finalText = '', interim = '';
      for (var i = event.resultIndex; i < event.results.length; i++) {
        var t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += t; else interim += t;
      }
      if (finalText) {
        var piece = tidy(finalText.trim());
        piece = capitalise(state.base, piece);
        var sep = state.base && !/[\s\n]$/.test(state.base) && !/^[.,?:]/.test(piece) ? ' ' : '';
        state.base = state.base + sep + piece;
      }
      field.value = state.base + (interim ? (state.base ? ' ' : '') + interim : '');
      field.dispatchEvent(new Event('input', { bubbles: true }));
    };
    rec.onerror = function (event) {
      var msg = {
        'not-allowed': 'Microphone access was blocked. Allow the microphone for this site in your browser settings.',
        'service-not-allowed': 'Microphone access was blocked. Allow the microphone for this site in your browser settings.',
        'no-speech': 'No speech heard. Click the mic and try again.',
        'audio-capture': 'No microphone found. Plug in a microphone and try again.',
        'network': 'Voice typing needs an internet connection.'
      }[event.error] || ('Voice typing stopped: ' + event.error);
      status.textContent = msg; status.className = 'voice-status err';
    };
    rec.onend = function () {
      field.value = state.base;
      btn.classList.remove('recording'); btn.setAttribute('aria-pressed', 'false'); btn.title = 'Dictate with your voice';
      if (status.className.indexOf('err') === -1) { status.textContent = ''; status.className = 'voice-status'; }
      if (active === state) active = null;
    };
    try { rec.start(); } catch (e) { status.textContent = 'Could not start voice typing.'; status.className = 'voice-status err'; }
  }

  fields.forEach(function (field) {
    var wrap = document.createElement('div');
    wrap.className = 'voice-wrap' + (field.tagName === 'TEXTAREA' ? ' is-area' : '');
    field.parentNode.insertBefore(wrap, field);
    wrap.appendChild(field);
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'mic-btn no-print'; btn.title = 'Dictate with your voice';
    btn.setAttribute('aria-label', 'Dictate with your voice'); btn.setAttribute('aria-pressed', 'false');
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12h-2z"/></svg>';
    wrap.appendChild(btn);
    var status = document.createElement('small');
    status.className = 'voice-status';
    wrap.parentNode.insertBefore(status, wrap.nextSibling);

    if (!Recognition) {
      btn.disabled = true;
      btn.title = 'Voice typing works in Google Chrome or Microsoft Edge';
      return;
    }
    if (!window.isSecureContext) {
      btn.disabled = true;
      btn.title = 'Voice typing needs https:// or http://localhost';
      return;
    }
    btn.addEventListener('click', function () { start(field, btn, status); });
  });
  window.addEventListener('beforeunload', stop);
  document.addEventListener('submit', stop, true);
})();
