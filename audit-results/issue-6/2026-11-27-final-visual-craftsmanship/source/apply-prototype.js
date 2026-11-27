(() => {
  const cssUrl = window.__SFE_VISUAL_CSS_URL__;
  if (cssUrl && !document.querySelector('link[data-visual-prototype]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssUrl;
    link.dataset.visualPrototype = 'true';
    document.head.appendChild(link);
  }

  const replaceText = (from, to) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      if (node.nodeValue && node.nodeValue.includes(from)) node.nodeValue = node.nodeValue.replaceAll(from, to);
    });
  };

  // Approved functional-copy direction integrated into the visual system.
  replaceText('Peek In', 'View photo');
  replaceText('WARN', 'Low-quality sample');

  // People edit drawer: distinguish controlled Tag from freeform Labels.
  replaceText('Use tags for roles, teams, access groups, or other searchable labels', 'Use labels for roles, teams, access groups, or other searchable keywords');
  replaceText('Type a tag and press Enter', 'Type a label and press Enter');
  [...document.querySelectorAll('label')].forEach((label) => {
    if (label.textContent.trim() === 'Tags') label.textContent = 'Labels';
  });

  // Person profile nested Events tab: avoid duplicate accessible name with primary Events navigation.
  [...document.querySelectorAll('[role="tab"],button')].forEach((el) => {
    if (el.textContent.trim() === 'Events' && el.closest('.people-profile-shell, .mantine-Card-root')) el.textContent = 'Event history';
  });


  // Photo details: distinguish authoritative event time from system-ingest time.
  // If no authoritative system-ingest timestamp is exposed for a media record, the row is omitted rather than invented.
  [...document.querySelectorAll('*')].filter((el) => el.children.length === 0 && el.textContent.trim() === 'Added').forEach((el) => {
    const panel = el.closest('.mantine-Card-root, .people-profile-panel, [class*="photo"]');
    if (panel && panel.textContent.includes('Face origin')) el.textContent = 'Event time';
  });

  // Profile actions: keep every capability, but move the long low-frequency reference-management
  // command into the existing overflow menu. The original button remains in the DOM and is invoked
  // by the overflow item, so this prototype demonstrates information hierarchy without losing function.
  const referenceButton = [...document.querySelectorAll('button')].find((button) => button.textContent.trim() === 'Manage Recognition References');
  if (referenceButton) referenceButton.classList.add('prototype-overflow-action');
  const enhanceOverflowMenus = () => {
    if (!referenceButton || window.innerWidth > 768) return;
    document.querySelectorAll('.mantine-Menu-dropdown').forEach((menu) => {
      if (menu.querySelector('[data-prototype-references]')) return;
      if (!menu.textContent.includes('Delete') && !menu.textContent.includes('Merge') && !menu.textContent.includes('Archive')) return;
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'mantine-Menu-item';
      item.dataset.prototypeReferences = 'true';
      item.style.width = 'calc(100% - 8px)';
      item.style.textAlign = 'left';
      item.textContent = 'Manage recognition references';
      item.addEventListener('click', () => referenceButton.click());
      menu.insertBefore(item, menu.firstChild);
    });
  };
  if (!window.__sfePrototypeMenuObserver) {
    window.__sfePrototypeMenuObserver = new MutationObserver(enhanceOverflowMenus);
    window.__sfePrototypeMenuObserver.observe(document.body, { childList: true, subtree: true });
  }
  enhanceOverflowMenus();


  // Owner setup: keep validation adjacent to the password field and keep requirements readable.
  const passwordError = [...document.querySelectorAll('*')].find((el) => el.children.length === 0 && el.textContent.trim() === 'Password must be between 12 and 256 characters');
  if (passwordError && !document.querySelector('.prototype-field-feedback')) {
    let banner = passwordError.closest('.mantine-Alert-root');
    if (!banner) {
      let cursor = passwordError.parentElement;
      for (let depth = 0; cursor && depth < 5; depth += 1, cursor = cursor.parentElement) {
        if (String(cursor.className || '').includes('Alert')) banner = cursor;
      }
    }
    (banner || passwordError).classList.add('prototype-detached-validation');
    const passwordInput = document.querySelector('input[type="password"]');
    const wrapper = passwordInput?.closest('.mantine-InputWrapper-root') || passwordInput?.parentElement?.parentElement;
    if (wrapper) {
      const feedback = document.createElement('div');
      feedback.className = 'prototype-field-feedback';
      feedback.innerHTML = '<div class="prototype-field-error">Password must be between 12 and 256 characters.</div><div class="prototype-password-rules">Use 12–256 characters. A longer passphrase is easier to remember and harder to guess.</div>';
      wrapper.appendChild(feedback);
    }
  }


  // Date filters: propose unambiguous ISO-style entry/display rather than locale-dependent mm/dd/yyyy.
  document.querySelectorAll('input[type="date"]').forEach((input) => {
    input.type = 'text';
    input.setAttribute('inputmode', 'numeric');
    if (!input.value) input.placeholder = 'yyyy-mm-dd';
  });

  // Events: unknown is neutral, not success.
  [...document.querySelectorAll('.mantine-Badge-root')].forEach((badge) => {
    if (badge.textContent.trim() === 'Unknown') {
      badge.style.background = 'var(--sentriface-muted-surface)';
      badge.style.color = 'var(--sentriface-tab-color)';
      badge.style.border = '1px solid var(--sentriface-border)';
    }
  });
})();
