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

let settingsModal;

class Setting {
  constructor(name, defaultValue, setter) {
    this.name = name;
    this.defaultValue = defaultValue;
    this.setValue = setter;
  }

  setElement() {
    throw new TypeError('Abstract methods should be implemented.');
  }

  load() {
    let value = JSON.parse(localStorage.getItem(this.name));
    this.value = value === null ? this.defaultValue : value;
    try {
      this.setValue(this.value);
    } catch (error) {
      console.error(`Failed to apply setting "${this.name}" With value:`, this.value);
      console.error(error);
    }
  }

  update() {
    throw new TypeError('Abstract methods should be implemented.');
  }

}

class CheckboxSetting extends Setting {

  setElement() {
    let element = document.querySelector(`input[name=${this.name}]`);
    element.checked = this.value;
  }

  update(element) {
    localStorage.setItem(this.name, element.checked);
    this.setValue(element.checked);
  }

}

class RadioSetting extends Setting {

  setElement() {
    let element = document.querySelector(`input[name=${this.name}][value=${this.value}]`);
    element.checked = true;
  }

  update(element) {
    localStorage.setItem(this.name, `"${element.value}"`);
    this.setValue(element.value);
  }

}

function getRootAttributeToggle(attributeName, valueName) {
  function toggleRootAttribute(set) {
    if (set) {
      document.documentElement.setAttribute(`data-${attributeName}`, valueName);
    } else {
      document.documentElement.removeAttribute(`data-${attributeName}`);
    }
  }
  return toggleRootAttribute;
}

function setTheme(value) {
  if (value === 'automatic') {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }
  else {
    document.documentElement.setAttribute('data-theme', value);
  }
}

const settings = [
  new CheckboxSetting('useSerifFont', false, getRootAttributeToggle('font', 'serif')),
  new RadioSetting('setTheme', 'automatic', setTheme)
]

function updateSetting(element) {
  let setting = settings.find((s) => s.name === element.name);
  if (setting) {
    setting.update(element);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  settingsModal = new Modal(document.querySelector('div#settings.modal'));
  for (const setting of settings) {
    setting.load();
    setting.setElement();
  }
});
