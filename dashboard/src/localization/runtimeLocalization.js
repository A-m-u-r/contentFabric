import { useEffect } from 'react';
import { ruAttributes, ruPatterns, ruText } from './ru';

const TEXT_ATTRIBUTE_NAMES = ['title', 'placeholder', 'aria-label', 'alt'];
const SKIP_TEXT_TAGS = new Set(['SCRIPT', 'STYLE', 'CODE', 'PRE']);

function preserveOuterWhitespace(original, translated) {
  const leading = original.match(/^\s*/)?.[0] || '';
  const trailing = original.match(/\s*$/)?.[0] || '';
  return `${leading}${translated}${trailing}`;
}

function translateString(value) {
  if (typeof value !== 'string') return value;

  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) return value;

  const direct = ruText[normalized] || ruAttributes[normalized];
  if (direct) return preserveOuterWhitespace(value, direct);

  for (const [pattern, replacement] of ruPatterns) {
    if (pattern.test(normalized)) {
      pattern.lastIndex = 0;
      return preserveOuterWhitespace(value, normalized.replace(pattern, replacement));
    }
  }

  return value;
}

function localizeElementAttributes(element) {
  for (const attrName of TEXT_ATTRIBUTE_NAMES) {
    if (!element.hasAttribute(attrName)) continue;
    const current = element.getAttribute(attrName);
    const translated = translateString(current);
    if (translated !== current) element.setAttribute(attrName, translated);
  }
}

function shouldSkipTextNode(textNode) {
  const parent = textNode.parentElement;
  if (!parent) return true;
  if (SKIP_TEXT_TAGS.has(parent.tagName)) return true;
  if (parent.closest('[data-localization-skip]')) return true;
  return false;
}

function localizeTextNode(textNode) {
  if (shouldSkipTextNode(textNode)) return;
  const current = textNode.textContent;
  const translated = translateString(current);
  if (translated !== current) textNode.textContent = translated;
}

function localizeNode(node) {
  if (!node) return;

  if (node.nodeType === Node.TEXT_NODE) {
    localizeTextNode(node);
    return;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) return;

  localizeElementAttributes(node);

  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    localizeTextNode(current);
    current = walker.nextNode();
  }

  for (const element of node.querySelectorAll?.('*') || []) {
    localizeElementAttributes(element);
  }
}

function patchAlert() {
  const originalAlert = window.alert;
  window.alert = (message) => originalAlert(translateString(message));
  return () => {
    window.alert = originalAlert;
  };
}

export function useRuntimeLocalization(locale = 'ru') {
  useEffect(() => {
    if (locale !== 'ru' || typeof document === 'undefined') return undefined;

    const root = document.body;
    localizeNode(root);
    const restoreAlert = patchAlert();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          localizeTextNode(mutation.target);
          continue;
        }

        if (mutation.type === 'attributes') {
          localizeElementAttributes(mutation.target);
          continue;
        }

        for (const addedNode of mutation.addedNodes) {
          localizeNode(addedNode);
        }
      }
    });

    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: TEXT_ATTRIBUTE_NAMES,
    });

    return () => {
      observer.disconnect();
      restoreAlert();
    };
  }, [locale]);
}
