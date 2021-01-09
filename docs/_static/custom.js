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

'use-strict';

let activeModal = null;
let bottomHeightThreshold, sections;
let hamburgerToggle;
let mobileSearch;
let sidebar;

class Modal {
  constructor(element) {
    this.element = element;
  }

  close() {
    activeModal = null;
    this.element.style.display = 'none'
  }

  open() {
    if (activeModal) {
      activeModal.close();
    }
    activeModal = this;
    this.element.style.display = 'flex'
  }
}

class SearchBar {

  constructor() {
    this.box = document.querySelector('nav.mobile-only');
    this.bar = document.querySelector('nav.mobile-only input[type="search"]');
    this.openButton = document.getElementById('open-search');
    this.closeButton = document.getElementById('close-search');
  }

  open() {
    this.openButton.hidden = true;
    this.closeButton.hidden = false;
    this.box.style.top = "100%";
    this.bar.focus();
  }

  close() {
    this.openButton.hidden = false;
    this.closeButton.hidden = true;
    this.box.style.top = "0";
  }

}

document.addEventListener('DOMContentLoaded', () => {
  mobileSearch = new SearchBar();

  bottomHeightThreshold = document.documentElement.scrollHeight - 30;
  sections = document.querySelectorAll('section');
  hamburgerToggle = document.getElementById('hamburger-toggle');

  if (hamburgerToggle) {
    hamburgerToggle.addEventListener('click', (e) => {
      sidebar.element.classList.toggle('sidebar-toggle');
      let button = hamburgerToggle.firstElementChild;
      if (button.textContent == 'menu') {
        button.textContent = 'close';
      }
      else {
        button.textContent = 'menu';
      }
    });
  }

  const tables = document.querySelectorAll('.py-attribute-table[data-move-to-id]');
  tables.forEach(table => {
    let element = document.getElementById(table.getAttribute('data-move-to-id'));
    let parent = element.parentNode;
    // insert ourselves after the element
    parent.insertBefore(table, element.nextSibling);
  });
});

document.addEventListener('keydown', (event) => {
  if (event.code == "Escape" && activeModal) {
    activeModal.close();
  }
});
