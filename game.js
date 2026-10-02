(function () {
  const game = (window.EXST_GAMES || []).find((g) => g.id === new URLSearchParams(location.search).get('id'));
  const title = document.getElementById('gameTitle'), frame = document.getElementById('gameFrame');
  if (!game) { title.textContent = 'Game not found'; return; }
  title.textContent = game.title; document.getElementById('gameMeta').textContent = game.version || '';
  frame.src = game.path; document.getElementById('openDirect').href = game.path;
  document.getElementById('fullscreenGame').onclick = () => frame.requestFullscreen?.();
  document.getElementById('reloadGame').onclick = () => frame.contentWindow.location.reload();
})();
