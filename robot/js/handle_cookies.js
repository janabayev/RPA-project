// Best-effort click on the cookie consent button.
// Searches the normal DOM and open shadow roots (some consent tools render inside a shadow DOM).
// Prefers "reject / only necessary" over "accept all".
// Returns the clicked button text, or '' if nothing was found.
var patterns = [
    /nur (technisch )?notwendige|ablehnen|alle ablehnen|reject/i,
    /alle akzeptieren|akzeptieren|zustimmen|einverstanden|accept/i
];

function collectButtons(root, acc) {
    root.querySelectorAll('button, [role="button"], a.button').forEach(function (b) { acc.push(b); });
    root.querySelectorAll('*').forEach(function (el) {
        if (el.shadowRoot) { collectButtons(el.shadowRoot, acc); }
    });
    return acc;
}

var buttons = collectButtons(document, []);
for (var p = 0; p < patterns.length; p++) {
    for (var i = 0; i < buttons.length; i++) {
        var text = (buttons[i].innerText || buttons[i].textContent || '').trim();
        if (text && text.length < 60 && patterns[p].test(text)) {
            buttons[i].click();
            return text;
        }
    }
}
return '';
