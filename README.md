# digest-site — публичен сайт с дайджестите

Новини, дневен дайджест със събития, Подари Време, RADAR действия,
табло с коли и AI план за учене. Всичко, което Muse генерира като HTML,
се качва тук автоматично.

Адрес: https://frashev.github.io/digest-site/

Как работи:
- Muse генерира HTML файловете в своя workspace.
- `site-sync.py` (на Muse, на всеки час) копира новите/променените
  файлове в тази папка през SSH и пуска `publish.ps1`.
- `publish.ps1` (на този компютър) генерира `index.html` през
  `build-index.py`, commit-ва промените и ги push-ва към GitHub.
- GitHub Pages сервира сайта. Push-ът става от този компютър през
  SSH ключ (`~/.ssh/id_rsa_github`), затова не иска одобрения
  в чата на Muse и не иска `gh auth login`.
