/* Parse the small, human-editable catalog files used by the arcade. */
(function () {
  function parse(text) {
    return String(text || '').split(/\n\s*\[game\]\s*\n/i).slice(1).map((block) => {
      const item = {};
      block.split(/\r?\n/).forEach((line) => {
        const at = line.indexOf('=');
        if (at > 0) item[line.slice(0, at).trim()] = line.slice(at + 1).trim();
      });
      return item;
    }).filter((item) => item.id && item.title && item.path);
  }
  function parseFolders(text) {
    return String(text || '').split(/\n\s*\[folder\]\s*\n/i).slice(1).map((block) => {
      const item = {};
      block.split(/\r?\n/).forEach((line) => {
        const at = line.indexOf('=');
        if (at > 0) item[line.slice(0, at).trim()] = line.slice(at + 1).trim();
      });
      item.games = (item.games || '').split(',').map((id) => id.trim()).filter(Boolean);
      return item;
    }).filter((item) => item.id && item.title && item.available !== 'false');
  }
  window.EXST_GAMES = parse(window.EXST_GAMES_TEXT);
  window.EXST_FOLDERS = parseFolders(window.EXST_FOLDERS_TEXT);
})();
