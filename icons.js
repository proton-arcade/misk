(function () {
  const paths = {
    home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
    search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    add: '<path d="M12 5v14M5 12h14"/>',
    play: '<path d="m8 5 12 7-12 7z" fill="currentColor" stroke="none"/>',
    sort: '<path d="M8 4v16m0 0-3-3m3 3 3-3M16 20V4m0 0 3 3m-3-3-3 3"/>',
    arrow_back: '<path d="m15 18-6-6 6-6M9 12h12"/>',
    'arrow-up-right': '<path d="M7 17 17 7M7 7h10v10"/>',
    x: '<path d="m6 6 12 12M18 6 6 18"/>',
  };
  document.querySelectorAll('[data-icon]').forEach((element) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    element.classList.add('icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.innerHTML = paths[element.dataset.icon] || '<circle cx="12" cy="12" r="8"/>';
    element.replaceChildren(svg);
  });
})();
