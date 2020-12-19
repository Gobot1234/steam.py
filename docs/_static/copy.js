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

const COPY = "content_copy";
const COPIED = "done";

const copy = async (obj) => {
  // <span class="copy"><span class="material-icons">{{text}}</span></span>
  await navigator.clipboard.writeText(obj.children[1].innerText).then(
    () => {
      let icon = obj.children[0].children[0];
      icon.textContent = COPIED;
      setTimeout(() => (icon.textContent = COPY), 2500);
    },
    (r) => alert("Could not copy codeblock:\n" + r.toString())
  );
};

document.addEventListener("DOMContentLoaded", () => {
  let allCodeblocks = document.querySelectorAll("div[class='highlight']");

  for (let codeblock of allCodeblocks) {
    codeblock.parentNode.className += " relative-copy";
    let copyEl = document.createElement("span");
    copyEl.addEventListener("click", () => copy(codeblock));
    copyEl.className = "copy";
    copyEl.setAttribute("aria-label", "Copy Code");
    copyEl.setAttribute("title", "Copy Code");

    let copyIcon = document.createElement("span");
    copyIcon.className = "material-icons";
    copyIcon.textContent = COPY;
    copyEl.append(copyIcon);

    codeblock.prepend(copyEl);
  }
});
