// Collects all links on the current search results page that point to a job detail page.
// karriere.at job detail URLs look like https://www.karriere.at/jobs/1234567
// Matching on the URL pattern is more stable than matching on CSS class names, which change often.
var links = Array.from(document.querySelectorAll('a[href]'))
    .map(function (a) { return a.href.split('?')[0].split('#')[0]; })
    .filter(function (h) { return /\/jobs\/\d+\/?$/.test(h); });
return Array.from(new Set(links));
