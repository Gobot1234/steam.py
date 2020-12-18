/*
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
*/

"use-strict";

let queryBeingDone = null;
let pattern = null;

const escapedRegex = /[-\/\\^$*+?.()|[\]{}]/g;
function escapeRegex(e) {
    return e.replace(escapedRegex, "\\$&");
}

// for some reason Sphinx shows some entries twice
// if something has been scored already I'd rather sort it to the bottom
const beenScored = new Set();

function __score(haystack, regex) {
    let match = regex.exec(haystack);
    if (match == null) {
        return Number.MAX_VALUE;
    }
    let subLength = match[0].length;
    let start = match.index;
    return (subLength * 1000 + start) / 1000.0;
}

// unused for now
function __cleanNamespaces(query) {
    return query.replace(/(steam\.(ext\.)?)?(.+)/, "$3");
}

Scorer = {
    // Implement the following function to further tweak the score for each result
    // The function takes a result array [filename, title, anchor, descr, score]
    // and returns the new score.
    score: (result) => {
        // only inflate the score of things that are actual API reference things
        const [, title, , , score] = result;

        if (pattern !== null && title.startsWith("steam.")) {
            let _score = __score(title, pattern);
            if (_score === Number.MAX_VALUE) {
                return score;
            }
            if (beenScored.has(title)) {
                return 0;
            }
            beenScored.add(title);
            let newScore = 100 + queryBeingDone.length - _score;
            // console.log(`${title}: ${score} -> ${newScore} (${_score})`);
            return newScore;
        }
        return score;
    },

    // query matches the full name of an object
    objNameMatch: 15,
    // or matches in the last dotted part of the object name
    objPartialMatch: 11,
    // Additive scores depending on the priority of the object
    objPrio: {
        0: 15, // used to be importantResults
        1: 7, // used to be objectResults
        2: -5, // used to be unimportantResults
    },
    //  Used when the priority is not in the mapping.
    objPrioDefault: 0,

    // query found in title
    title: 15,
    partialTitle: 7,
    // query found in terms
    term: 5,
    partialTerm: 2,
};

document.addEventListener("DOMContentLoaded", () => {
    const params = new URLSearchParams(window.location.search);
    queryBeingDone = params.get("q");
    if (queryBeingDone) {
        let pattern = Array.from(queryBeingDone).map(escapeRegex).join(".*?");
        pattern = new RegExp(pattern, "i");
    }
});
