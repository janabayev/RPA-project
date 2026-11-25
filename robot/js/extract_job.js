// Extracts job data from a job detail page.
// 1st choice: the schema.org "JobPosting" JSON-LD block that most job portals embed for Google Jobs.
//             It is machine-readable and independent of the page layout.
// 2nd choice (fallback): visible page elements (h1 + main content text).
var out = {
    title: '', company: '', location: '', date_posted: '',
    employment_type: '', description: '', source: 'none'
};

function htmlToText(html) {
    var div = document.createElement('div');
    div.innerHTML = html || '';
    return div.textContent || '';
}

function findJobPosting(node) {
    if (!node) { return null; }
    if (Array.isArray(node)) {
        for (var i = 0; i < node.length; i++) {
            var r = findJobPosting(node[i]);
            if (r) { return r; }
        }
        return null;
    }
    if (typeof node === 'object') {
        var t = node['@type'];
        if (t === 'JobPosting' || (Array.isArray(t) && t.indexOf('JobPosting') >= 0)) { return node; }
        if (node['@graph']) { return findJobPosting(node['@graph']); }
    }
    return null;
}

var scripts = document.querySelectorAll('script[type="application/ld+json"]');
for (var s = 0; s < scripts.length; s++) {
    try {
        var jp = findJobPosting(JSON.parse(scripts[s].textContent));
        if (jp) {
            out.title = jp.title || '';
            out.company = (jp.hiringOrganization && jp.hiringOrganization.name) || '';
            var loc = Array.isArray(jp.jobLocation) ? jp.jobLocation[0] : jp.jobLocation;
            if (loc && loc.address) {
                out.location = [loc.address.addressLocality, loc.address.addressRegion]
                    .filter(Boolean).join(', ');
            }
            out.date_posted = jp.datePosted || '';
            out.employment_type = Array.isArray(jp.employmentType)
                ? jp.employmentType.join(', ') : (jp.employmentType || '');
            out.description = htmlToText(jp.description);
            out.source = 'json-ld';
            break;
        }
    } catch (e) { /* invalid JSON block - ignore */ }
}

// Fallbacks if JSON-LD is missing or incomplete
if (!out.title) {
    var h1 = document.querySelector('h1');
    out.title = h1 ? h1.innerText : document.title;
}
if (!out.description || out.description.length < 200) {
    var main = document.querySelector('main') || document.querySelector('article') || document.body;
    out.description = main.innerText;
    out.source = (out.source === 'json-ld') ? 'json-ld+main' : 'main';
}
return out;
