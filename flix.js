(function () {
  const catalog = window.EXST_GAMES || [];
  const rows = document.getElementById('rows');
  const grid = document.getElementById('searchGrid');
  const storageKey = 'exstHomeSections';
  let settings = {};
  try { settings = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch (_) { settings = {}; }

  function makeCard(game) {
    const link = document.createElement('a');
    link.className = 'game-card';
    link.href = '#detailsPage';
    link.dataset.details = game.id;
    const image = document.createElement('img');
    image.src = `website/${game.icon || 'assets/images/default-game.svg'}`;
    image.alt = '';
    image.onerror = () => { image.src = 'website/assets/images/default-game.svg'; };
    const title = document.createElement('span');
    title.textContent = game.title;
    link.append(image, title);
    return link;
  }

  function renderSections() {
    rows.replaceChildren();
    const groups = new Map();
    catalog.forEach((game) => {
      (game.tags || 'Games').split(',').map((tag) => tag.trim()).filter(Boolean).forEach((tag) => {
        if (settings[tag] === false) return;
        if (!groups.has(tag)) groups.set(tag, []);
        groups.get(tag).push(game);
      });
    });
    if (!groups.size && catalog.length) groups.set('Games', catalog);
    function appendRow(label, items) {
      const section = document.createElement('section');
      section.className = 'flix-row';
      const heading = document.createElement('h2');
      heading.textContent = label;
      const cards = document.createElement('div');
      cards.className = 'row-posters';
      items.forEach((game) => cards.append(makeCard(game)));
      section.append(heading, cards);
      rows.append(section);
    }
    (window.EXST_FOLDERS || []).forEach((folder) => {
      if (settings[`collection:${folder.id}`] === false) return;
      const collectionGames = folder.games.map((id) => catalog.find((game) => game.id === id)).filter(Boolean);
      if (collectionGames.length) appendRow(folder.title, collectionGames);
    });
    groups.forEach((items, label) => appendRow(label, items));
  }

  // Only games explicitly marked `hero=true` belong in the banner. Filtering
  // preserves their order in data/games.js; all other catalog entries are skipped.
  const spotlightGames = catalog.filter((game) => game.hero === 'true');
  const heroDots = document.getElementById('heroDots');
  const heroCover = document.getElementById('heroCover');
  const heroTitle = document.getElementById('heroTitle');
  let activeSpotlight = 0;

  function showSpotlight(index) {
    if (!spotlightGames.length) return;
    activeSpotlight = (index + spotlightGames.length) % spotlightGames.length;
    const game = spotlightGames[activeSpotlight];
    heroTitle.textContent = game.title;
    document.getElementById('heroOverview').textContent = game.description || '';
    document.getElementById('heroKicker').textContent = game.version || 'Featured game';
    document.getElementById('heroMeta').textContent = (game.tags || '').split(',').map((tag) => tag.trim()).filter(Boolean).join(' · ');
    document.getElementById('heroCategories').textContent = '';
    document.getElementById('heroPlay').dataset.play = game.id;
    document.getElementById('heroDetails').dataset.details = game.id;
    heroCover.style.backgroundImage = `linear-gradient(90deg,#111,transparent),url("website/${game.icon || 'assets/images/default-game.svg'}")`;
    heroDots.querySelectorAll('button').forEach((dot, dotIndex) => {
      const selected = dotIndex === activeSpotlight;
      dot.classList.toggle('selected', selected);
      dot.setAttribute('aria-pressed', String(selected));
    });
  }

  spotlightGames.forEach((game, index) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.setAttribute('aria-label', `Show ${game.title}`);
    dot.setAttribute('aria-pressed', 'false');
    dot.addEventListener('click', () => {
      showSpotlight(index);
      restartSpotlightTimer();
    });
    heroDots.append(dot);
  });
  if (spotlightGames.length < 2) heroDots.hidden = true;
  showSpotlight(0);

  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let spotlightTimer;
  function restartSpotlightTimer() {
    window.clearInterval(spotlightTimer);
    if (reduceMotion || spotlightGames.length < 2) return;
    spotlightTimer = window.setInterval(() => {
      const home = document.getElementById('page-home');
      if (document.hidden || home.hidden || heroDots.matches(':hover') || heroDots.contains(document.activeElement)) return;
      showSpotlight(activeSpotlight + 1);
    }, 5000);
  }
  heroDots.addEventListener('mouseenter', () => window.clearInterval(spotlightTimer));
  heroDots.addEventListener('mouseleave', restartSpotlightTimer);
  heroDots.addEventListener('focusin', () => window.clearInterval(spotlightTimer));
  heroDots.addEventListener('focusout', restartSpotlightTimer);
  document.addEventListener('visibilitychange', restartSpotlightTimer);
  restartSpotlightTimer();

  renderSections();
  catalog.forEach((game) => grid.append(makeCard(game)));
  const count = document.getElementById('searchCount');
  if (count) count.textContent = `${catalog.length} games`;

  // The spotlight is controlled only by the hero=true flag in data/games.js.
  // This editor controls visibility of tag-based rows and collections only.
  document.getElementById('editSections')?.addEventListener('click', () => {
    const dialog = document.getElementById('sectionsDialog');
    const content = document.getElementById('sectionsEditor');
    content.replaceChildren();
    const heading = document.createElement('h3'); heading.textContent = 'Home page sections'; content.append(heading);
    const tags = [...new Set(catalog.flatMap((game) => (game.tags || 'Games').split(',').map((tag) => tag.trim()).filter(Boolean)))];
    tags.forEach((tag) => {
      const label = document.createElement('label'); label.className = 'section-editor-toggle';
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = settings[tag] !== false;
      checkbox.dataset.section = tag;
      label.append(checkbox, document.createTextNode(` Show ${tag} section`)); content.append(label);
    });
    (window.EXST_FOLDERS || []).forEach((folder) => {
      const label = document.createElement('label'); label.className = 'section-editor-toggle';
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
      checkbox.checked = settings[`collection:${folder.id}`] !== false;
      checkbox.dataset.collection = folder.id;
      label.append(checkbox, document.createTextNode(` Show collection: ${folder.title}`)); content.append(label);
    });
    dialog.showModal();
  });
  document.getElementById('saveSections')?.addEventListener('click', () => {
    const dialog = document.getElementById('sectionsDialog');
    const next = {};
    document.querySelectorAll('#sectionsEditor [data-section]').forEach((checkbox) => { next[checkbox.dataset.section] = checkbox.checked; });
    document.querySelectorAll('#sectionsEditor [data-collection]').forEach((checkbox) => { next[`collection:${checkbox.dataset.collection}`] = checkbox.checked; });
    settings = next;
    try { localStorage.setItem(storageKey, JSON.stringify(settings)); } catch (_) { /* session remains usable */ }
    location.reload();
  });
  document.getElementById('closeSections')?.addEventListener('click', () => document.getElementById('sectionsDialog').close());

  document.querySelectorAll('#footerBar button').forEach((button) => button.addEventListener('click', () => {
    const name = button.getAttribute('ref');
    document.querySelectorAll('.flix-page').forEach((page) => { page.hidden = page.id !== `page-${name}`; });
    document.querySelectorAll('#footerBar button').forEach((item) => item.classList.toggle('active', item === button));
  }));
  document.getElementById('searchInput')?.addEventListener('input', (event) => {
    const query = event.target.value.toLowerCase();
    grid.replaceChildren(...catalog.filter((game) => game.title.toLowerCase().includes(query)).map(makeCard));
  });
  function showDetails(game) {
    if (!game) return;
    document.getElementById('detailsHeadTitle').textContent = game.title;
    document.getElementById('detailsTitle').textContent = game.title;
    document.getElementById('detailsMeta').textContent = game.version || '';
    document.getElementById('detailsOverview').textContent = game.description || 'No description available.';
    const tags = document.getElementById('detailsTags');
    tags.replaceChildren(...(game.tags || '').split(',').map((tag) => tag.trim()).filter(Boolean).map((tag) => {
      const chip = document.createElement('span'); chip.textContent = tag; return chip;
    }));
    document.getElementById('detailsCover').style.backgroundImage = `linear-gradient(to bottom, transparent 45%, #101010 100%), url("website/${game.icon || 'assets/images/default-game.svg'}")`;
    document.getElementById('detailsDirect').href = `website/${game.path}`;
    document.getElementById('detailsPlay').dataset.play = game.id;
    const panel = document.getElementById('detailsPage');
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add('open'));
    document.body.classList.add('noscroll');
  }
  function closeDetails() {
    const panel = document.getElementById('detailsPage');
    panel.classList.remove('open');
    document.body.classList.remove('noscroll');
    window.setTimeout(() => { panel.hidden = true; }, 220);
  }
  document.getElementById('detailsClose')?.addEventListener('click', closeDetails);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !document.getElementById('detailsPage').hidden) closeDetails(); });

  document.addEventListener('click', (event) => {
    const detailTarget = event.target.closest('[data-details]');
    if (detailTarget) {
      event.preventDefault();
      showDetails(catalog.find((game) => game.id === detailTarget.dataset.details));
      return;
    }
    const button = event.target.closest('[data-play]'); if (!button) return;
    const game = catalog.find((item) => item.id === button.dataset.play) || hero; if (!game) return;
    const mode = localStorage.getItem('openMode') || 'page';
    const url = `website/${game.path}`;
    if (mode === 'same') location.href = url;
    else if (mode === 'new') window.open(url, '_blank', 'noopener');
    else location.href = `website/game.html?id=${encodeURIComponent(game.id)}`;
  });
  document.getElementById('openMode')?.addEventListener('change', (event) => localStorage.setItem('openMode', event.target.value));
  const mode = document.getElementById('openMode'); if (mode) mode.value = localStorage.getItem('openMode') || 'page';
})();