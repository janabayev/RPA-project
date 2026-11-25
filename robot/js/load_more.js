// Clicks the "Weitere Jobs anzeigen" button below the search results.
// karriere.at has no page URLs (?page=2 returns page 1 again): further results are loaded
// into the same page by this button, about 15 jobs per click.
// Returns true if a visible, enabled button was clicked, false if there is none (all results shown).
var button = document.querySelector('button.m-loadMoreJobsButton__button');
if (!button) {
    // fallback in case the CSS class changes: find the button by its text
    button = Array.from(document.querySelectorAll('button')).find(function (b) {
        return /weitere jobs|mehr jobs/i.test(b.textContent || '');
    });
}
if (!button || button.disabled || button.offsetParent === null) {
    return false;
}
button.scrollIntoView({block: 'center'});
button.click();
return true;
