# Questo programma cerca film o serie TV, naviga verso la loro pagina,
# e cerca di estrare il link .m3u8 del flusso video.
# La ricerca e la navigazione usano Camoufox (basato su Playwright) per una migliore
# gestione anti-bot e un approccio asincrono.
# L'estrazione del link finale avviene analizzando direttamente la pagina del player.

# Importiamo le librerie necessarie.
import asyncio
from camoufox import AsyncCamoufox
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import get_addon_path
from bs4 import BeautifulSoup
import re
import urllib.parse
import argparse
import sys
from curl_cffi import requests
import jsbeautifier
import os
import subprocess
import shutil
from pathlib import Path
from tqdm import tqdm
import platform
import zipfile
import tarfile
import time

# --- CONFIGURAZIONE GLOBALE ---

# Codici ANSI per i colori del testo.
class Bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Variabili globali
BASE_URL = "https://onlineserietv.com"
SEARCH_URL = f"{BASE_URL}/?s="
PROGRESS_BAR_COLOR = "cyan"
FFMPEG_BIN_PATH: str | None = None
FFPROBE_BIN_PATH: str | None = None
DISABLE_PROGRESS = False
ADDON_PATH = get_addon_path()

# =========================================================================
# FUNZIONI DI RICERCA E NAVIGAZIONE (con Camoufox/Playwright)
# =========================================================================

async def search_content(page, title):
    """Cerca un contenuto e restituisce una lista di risultati."""
    print(f"Sto cercando: {Bcolors.WARNING}{title}{Bcolors.ENDC}...")
    search_query = urllib.parse.quote_plus(title)
    url = f"{SEARCH_URL}{search_query}"
    
    try:
        await page.goto(url, wait_until='domcontentloaded')
        await page.wait_for_selector("div#box_movies", timeout=45000)
        print(f"{Bcolors.OKGREEN}Pagina dei risultati caricata.{Bcolors.ENDC}")
    except Exception as e:
        print(f"{Bcolors.FAIL}Errore nella ricerca: {e}{Bcolors.ENDC}")
        return []

    soup = BeautifulSoup(await page.content(), 'html.parser')
    movie_items = soup.find_all('div', class_='movie')
    
    results = []
    for item in movie_items:
        title_tag = item.find('h2')
        link_tag = item.find('a')
        if title_tag and link_tag:
            content_type = "Serie TV" if "/serietv/" in link_tag['href'] else "Film"
            results.append({
                'title': title_tag.text.strip(),
                'link': link_tag['href'],
                'type': content_type
            })
    return results

# =========================================================================
# FUNZIONI HELPER (DOWNLOAD, FFMPEG, PARSING) - INVARIATE
# =========================================================================

def sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', " ", name)
    return re.sub(r'\s+', " ", safe).strip()

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def parse_selection_arg(arg_value: str):
    if not arg_value or str(arg_value).lower() == "all": return "all"
    selected: set[int] = set()
    for part in str(arg_value).split(','):
        part = part.strip()
        if not part: continue
        if '-' in part:
            a, b = part.split('-', 1)
            try: start, end = int(a), int(b)
            except ValueError: continue
            selected.update(range(min(start, end), max(start, end) + 1))
        else:
            try: selected.add(int(part))
            except ValueError: continue
    return selected if selected else "all"

def _download_file(url: str, dest_path: Path) -> None:
    # Questa funzione rimane sincrona
    r = requests.get(url, stream=True, impersonate='chrome110')
    r.raise_for_status()
    try:
        total = int(r.headers.get('content-length', 0))
        with open(dest_path, 'wb') as f, tqdm(
            total=total, unit='B', unit_scale=True, desc=f"Scarico {dest_path.name}", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"
        ) as pbar:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    finally:
        r.close()

def _extract_archive(archive_path: Path, target_dir: Path) -> None:
    print(f"Estrazione di {archive_path.name}...")
    target_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.name.endswith('.zip'):
        with zipfile.ZipFile(archive_path, 'r') as zf: zf.extractall(target_dir)
    elif archive_path.name.endswith(('.tar.gz', '.tgz', '.tar.xz')):
        with tarfile.open(archive_path, 'r:*') as tf: tf.extractall(target_dir)
    print("Estrazione completata.")

def _resolve_ffmpeg_binaries(bin_root: Path) -> tuple[str | None, str | None]:
    ffmpeg_path, ffprobe_path = None, None
    for root, _, files in os.walk(bin_root):
        for fn in files:
            low = fn.lower()
            if low == "ffmpeg" or low == "ffmpeg.exe": ffmpeg_path = str(Path(root) / fn)
            elif low == "ffprobe" or low == "ffprobe.exe": ffprobe_path = str(Path(root) / fn)
    return ffmpeg_path, ffprobe_path

def ensure_ffmpeg() -> bool:
    global FFMPEG_BIN_PATH, FFPROBE_BIN_PATH
    if FFMPEG_BIN_PATH and FFPROBE_BIN_PATH: return True

    sys_ffmpeg = shutil.which('ffmpeg')
    sys_ffprobe = shutil.which('ffprobe')
    if sys_ffmpeg and sys_ffprobe:
        FFMPEG_BIN_PATH, FFPROBE_BIN_PATH = sys_ffmpeg, sys_ffprobe
        print(f"{Bcolors.OKBLUE}ffmpeg trovato nel PATH di sistema.{Bcolors.ENDC}")
        return True

    script_dir = Path(__file__).resolve().parent
    bin_dir = script_dir / 'bin'
    
    ffmpeg_local, ffprobe_local = _resolve_ffmpeg_binaries(bin_dir)
    if ffmpeg_local and ffprobe_local:
        FFMPEG_BIN_PATH, FFPROBE_BIN_PATH = ffmpeg_local, ffprobe_local
        print(f"{Bcolors.OKBLUE}ffmpeg trovato nella cartella locale '{bin_dir}'.{Bcolors.ENDC}")
        return True

    os_name = platform.system().lower()
    bin_dir.mkdir(parents=True, exist_ok=True)
    print(f"{Bcolors.WARNING}ffmpeg non trovato. Tentativo di download per {os_name}...{Bcolors.ENDC}")

    archive_path = None
    try:
        if os_name == 'windows':
            url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
            archive_path = bin_dir / 'ffmpeg.zip'
            _download_file(url, archive_path)
            _extract_archive(archive_path, bin_dir)
        elif os_name == 'darwin':
            for tool in ['ffmpeg', 'ffprobe']:
                url = f'https://evermeet.cx/ffmpeg/{tool}-6.1.1.zip'
                archive_path = bin_dir / f'{tool}-mac.zip'
                _download_file(url, archive_path)
                _extract_archive(archive_path, bin_dir)
                archive_path.unlink()
        else: # Linux
            url = 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz'
            archive_path = bin_dir / 'ffmpeg-linux.tar.xz'
            _download_file(url, archive_path)
            _extract_archive(archive_path, bin_dir)

        if archive_path and archive_path.exists(): archive_path.unlink()

        ffmpeg_local, ffprobe_local = _resolve_ffmpeg_binaries(bin_dir)
        if ffmpeg_local and ffprobe_local:
            print(f"{Bcolors.OKGREEN}ffmpeg installato con successo in '{bin_dir}'.{Bcolors.ENDC}")
            if os_name != 'windows':
                try:
                    os.chmod(ffmpeg_local, 0o755)
                    os.chmod(ffprobe_local, 0o755)
                except Exception: pass
            FFMPEG_BIN_PATH, FFPROBE_BIN_PATH = ffmpeg_local, ffprobe_local
            return True
        else:
            print(f"{Bcolors.FAIL}Impossibile localizzare ffmpeg/ffprobe dopo il download.{Bcolors.ENDC}")
            return False
    except Exception as e:
        print(f"{Bcolors.FAIL}Download/estrazione ffmpeg fallita: {e}{Bcolors.ENDC}")
        if archive_path and archive_path.exists(): archive_path.unlink()
        return False

def _probe_duration_seconds(m3u8_url: str, referer: str) -> float | None:
    if not FFPROBE_BIN_PATH: return None
    try:
        cmd = [FFPROBE_BIN_PATH, "-v", "error", "-headers", f"Referer: {referer}\r\n", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", m3u8_url]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=20).strip()
        return float(out) if out and out != "N/A" else None
    except Exception: return None

def download_m3u8_to_mp4(m3u8_url: str, output_file: Path, referer: str = "https://flexy.stream/"):
    if not FFMPEG_BIN_PATH:
        print(f"{Bcolors.FAIL}ffmpeg non disponibile. Salto download.{Bcolors.ENDC}")
        return

    total_duration = _probe_duration_seconds(m3u8_url, referer)
    cmd = [FFMPEG_BIN_PATH, "-y", "-hide_banner", "-nostats", "-headers", f"Referer: {referer}\r\n", "-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", "-progress", "pipe:1", "-loglevel", "error", str(output_file)]
    
    print(f"{Bcolors.OKBLUE}Scarico in MP4: {output_file.name}{Bcolors.ENDC}")
    try:
        # La logica di download con la progress bar rimane sincrona
        if total_duration and not DISABLE_PROGRESS:
            pbar_args = {"total": int(total_duration), "unit": "s", "dynamic_ncols": True, "bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt}s ETA {remaining}"}
            try: pbar = tqdm(colour=PROGRESS_BAR_COLOR, **pbar_args)
            except TypeError: pbar = tqdm(**pbar_args)
            
            with pbar, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as proc:
                for line in proc.stdout:
                    if line.startswith("out_time_ms="):
                        ms = int(line.strip().split("=")[1])
                        pbar.n = min(ms // 1_000_000, pbar.total)
                        pbar.refresh()
                if proc.wait() != 0: raise subprocess.CalledProcessError(proc.returncode, cmd)
        else:
            subprocess.run(cmd, check=True)
        print(f"{Bcolors.OKGREEN}Download completato: {output_file}{Bcolors.ENDC}")
    except Exception as e:
        print(f"{Bcolors.FAIL}Errore ffmpeg per {output_file.name}: {e}{Bcolors.ENDC}")

# =========================================================================
# GESTIONE CONTENUTI (con Camoufox/Playwright)
# =========================================================================

async def get_page_title(page) -> str:
    """Estrae il titolo principale (h1) dalla pagina, altrimenti usa il titolo del tag <title>."""
    html = await page.content()
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    return (h1.text.strip() if h1 else await page.title()) or "Contenuto"

async def get_m3u8_link(page, page_url: str, s_num: int = 0, e_num: int = 0):
    """
    Versione finale con attese stabilizzate per la lettura del player
    e logging migliorato per evitare confusione.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"{Bcolors.OKCYAN}Apertura pagina: {page_url}{Bcolors.ENDC}")
                await page.goto(page_url, wait_until='domcontentloaded', timeout=4500)
            else:
                print(f"{Bcolors.OKCYAN}Tentativo {attempt + 1}/{max_retries}... Ricarico la pagina.{Bcolors.ENDC}")
                await page.reload(wait_until='domcontentloaded')
                await page.wait_for_timeout(200)

            # --- LOGICA DI SELEZIONE PLAYER STABILIZZATA ---
            try:
                player_selector = page.locator("select[name='sel_player']")
                # 1. Attende che il selettore sia visibile e stabile.
                await player_selector.wait_for(state='visible', timeout=500)
                # 2. Aggiunge una brevissima pausa per eliminare le race condition.
                await page.wait_for_timeout(500)
                
                current_player_value = await player_selector.input_value()

                # 3. Migliora il logging per chiarezza
                player_display_name = current_player_value if current_player_value else "Default (valore vuoto)"

                if current_player_value != 'fx':
                    print(f"{Bcolors.OKBLUE}Player attuale: '{player_display_name}'. Forzo la selezione di 'Flexy (fx)'...{Bcolors.ENDC}")
                    async with page.expect_navigation(wait_until='domcontentloaded', timeout=2000):
                        await player_selector.select_option("fx")
                    print(f"{Bcolors.OKGREEN}Pagina ricaricata con il player 'Flexy' selezionato.{Bcolors.ENDC}")
                else:
                    print(f"{Bcolors.OKGREEN}Player 'Flexy (fx)' è già selezionato. Si procede.{Bcolors.ENDC}")

            except Exception:
                print(f"{Bcolors.WARNING}Selettore del player non trovato, si procede con il player di default.{Bcolors.ENDC}")
            # --- FINE LOGICA STABILIZZATA ---

            captcha_locator = page.locator('input[name="capt"]')
            if await captcha_locator.is_visible(timeout=2000):
                raise Exception("CAPTCHA (player MaxStream) rilevato. Nuovo tentativo in corso.")

            try:
                await page.locator("img[src*='player.png']").click(timeout=1000)
            except Exception:
                print(f"{Bcolors.WARNING}Immagine player esterna non trovata o non necessaria.{Bcolors.ENDC}")

            iframe_selector = "iframe[src*='uprot.net/fxe'], iframe[src*='flexy.stream']"
            
            await page.wait_for_selector(iframe_selector, state='visible', timeout=3000)
            frame_locator = page.frame_locator(iframe_selector)
            
            try:
                print(f"{Bcolors.OKBLUE}Trovato iframe. Tento di cliccare sull'area del player video...{Bcolors.ENDC}")
                await frame_locator.locator('.video-js').click(timeout=1000)
                print(f"{Bcolors.OKGREEN}Area del player cliccata.{Bcolors.ENDC}")
                await page.wait_for_timeout(2000)
            except Exception:
                print(f"{Bcolors.WARNING}Area del player video non trovata o click non necessario.{Bcolors.ENDC}")

            iframe_source = await frame_locator.locator(':root').inner_html()

            soup = BeautifulSoup(iframe_source, 'html.parser')
            for script in soup.find_all("script", string=re.compile("eval")):
                data_js = jsbeautifier.beautify(script.string)
                match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)
                if match:
                    print(f"{Bcolors.OKGREEN}Link M3U8 trovato al tentativo {attempt + 1}.{Bcolors.ENDC}")
                    return match.group(1)
            
            raise Exception("Iframe trovato, ma lo script con il link M3U8 non è presente.")

        except Exception as e:
            print(f"{Bcolors.WARNING}Tentativo {attempt + 1} fallito: {str(e).splitlines()[0]}{Bcolors.ENDC}")
            if attempt + 1 == max_retries:
                print(f"{Bcolors.FAIL}Tutti i {max_retries} tentativi sono falliti.{Bcolors.ENDC}")
                
                debug_dir = Path.cwd() / "debug_screenshots"
                ensure_dir(debug_dir)
                
                filename = f"error_S{s_num:02d}E{e_num:02d}_{int(time.time())}.png"
                screenshot_path = debug_dir / filename
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"{Bcolors.WARNING}Screenshot dell'ultimo tentativo salvato in: {screenshot_path}{Bcolors.ENDC}")
                
                return None

    return None

async def enumerate_and_download_series(page, series_url: str, seasons_arg, episodes_arg, outdir: Path, delay: float):
    print(f"{Bcolors.OKGREEN}Apro la pagina della serie: {series_url}{Bcolors.ENDC}")
    # Aumentiamo il timeout del goto per dare tempo a eventuali reindirizzamenti anti-bot di risolversi
    await page.goto(series_url, wait_until='domcontentloaded', timeout=60000)

    try:
        # 1. ATTENDI L'ELEMENTO CHIAVE: Aspetta che l'iframe delle stagioni sia caricato.
        #    Questo conferma che abbiamo superato la pagina "Just a moment..." e siamo sulla pagina reale.
        iframe_selector = "iframe[src*='streaming-serie-tv']"
        print(f"{Bcolors.OKCYAN}Attendo il caricamento completo della pagina e del selettore di episodi...{Bcolors.ENDC}")
        await page.wait_for_selector(iframe_selector, timeout=30000)
        print(f"{Bcolors.OKGREEN}Pagina della serie caricata correttamente.{Bcolors.ENDC}")

        # 2. ORA È SICURO OTTENERE IL TITOLO: Dato che l'iframe esiste, siamo sulla pagina giusta.
        series_title = sanitize_filename(await get_page_title(page))
        print(f"{Bcolors.OKCYAN}Serie rilevata: {series_title}{Bcolors.ENDC}")

        # 3. Procedi come prima
        selection_page_url = await page.locator(iframe_selector).get_attribute("src")
        await page.goto(selection_page_url)

    except Exception as e:
        print(f"{Bcolors.FAIL}Iframe delle stagioni non rilevato o la pagina non si è caricata correttamente: {e}{Bcolors.ENDC}")
        # Aggiungiamo uno screenshot anche qui per il debug
        debug_dir = Path.cwd() / "debug_screenshots"
        ensure_dir(debug_dir)
        filename = f"error_series_page_{int(time.time())}.png"
        screenshot_path = debug_dir / filename
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"{Bcolors.WARNING}Screenshot salvato in: {screenshot_path}{Bcolors.ENDC}")
        return # Esce dalla funzione se non può procedere

    # Il resto della funzione rimane invariato...
    if seasons_arg == 'all' and episodes_arg == 'all':
        soup = BeautifulSoup(await page.content(), 'html.parser')
        seasons = soup.select('div.div_seasons a[href]')
        if not seasons: print(f"{Bcolors.FAIL}Nessuna stagione trovata.{Bcolors.ENDC}"); return
        
        print(f"\n{Bcolors.HEADER}--- Stagioni disponibili ---{Bcolors.ENDC}")
        col_width = max(len(s.text.strip()) for s in seasons) + 1
        for i, s in enumerate(seasons): print(f"{Bcolors.OKGREEN}| {i+1:<3} | {s.text.strip():<{col_width}} |{Bcolors.ENDC}")
        
        seasons_arg = input(f"{Bcolors.OKBLUE}Seleziona stagioni (es. 1,3-4 o 'all'): {Bcolors.ENDC}") or 'all'
        
        if re.match(r"^\d+$", seasons_arg):
            try:
                await page.goto(seasons[int(seasons_arg) - 1]['href'])
                ep_soup = BeautifulSoup(await page.content(), 'html.parser')
                episodes = ep_soup.select('div.div_episodes a[href]')
                print(f"\n{Bcolors.HEADER}--- Episodi disponibili ---{Bcolors.ENDC}")
                col_width = max(len(e.text.strip()) for e in episodes) + 1
                for i, e in enumerate(episodes): print(f"{Bcolors.OKGREEN}| {i+1:<3} | {e.text.strip():<{col_width}} |{Bcolors.ENDC}")
                episodes_arg = input(f"{Bcolors.OKBLUE}Seleziona episodi (es. 1,3-5 o 'all'): {Bcolors.ENDC}") or 'all'
            except (ValueError, IndexError): pass
            await page.goto(selection_page_url)

    seasons_filter, episodes_filter = parse_selection_arg(seasons_arg), parse_selection_arg(episodes_arg)
    episodes_to_process = []
    
    def _parse_href(h): return tuple(map(int, re.findall(r'\d+', h)[-3:])) if 'streaming-serie-tv' in h else None
    
    await page.goto(selection_page_url)
    soup_seasons = BeautifulSoup(await page.content(), 'html.parser')

    for season_link in soup_seasons.select('div.div_seasons a[href]'):
        parsed = _parse_href(season_link['href'])
        if not parsed or (seasons_filter != 'all' and parsed[1] not in seasons_filter): continue
        
        await page.goto(season_link['href'])
        soup_episodes = BeautifulSoup(await page.content(), 'html.parser')
        for ep_link in soup_episodes.select('div.div_episodes a[href]'):
            ep_parsed = _parse_href(ep_link['href'])
            if ep_parsed and (episodes_filter == 'all' or ep_parsed[2] in episodes_filter):
                episodes_to_process.append((ep_parsed[1], ep_parsed[2], ep_link['href']))

    print(f"\n{Bcolors.OKBLUE}Trovati {len(episodes_to_process)} episodi da scaricare.{Bcolors.ENDC}")
    for s_num, e_num, ep_url in sorted(list(set(episodes_to_process))):
        print(f"{Bcolors.HEADER}--- Processing S{s_num:02d}E{e_num:02d} ---{Bcolors.ENDC}")
        m3u8 = await get_m3u8_link(page, ep_url, s_num, e_num)
        if m3u8:
            season_dir = outdir / "Serie" / series_title / f"S{s_num:02d}"
            ensure_dir(season_dir)
            download_m3u8_to_mp4(m3u8, season_dir / f"{series_title} - S{s_num:02d}E{e_num:02d}.mp4")
            await asyncio.sleep(delay)
        else:
            print(f"{Bcolors.FAIL}Salto S{s_num:02d}E{e_num:02d} - M3U8 non trovato.{Bcolors.ENDC}")

# =========================================================================
# FUNZIONE PRINCIPALE (ASINCRONA)
# =========================================================================
async def main():
    parser = argparse.ArgumentParser(description='Cerca e scarica contenuti da onlineserietv.com')
    parser.add_argument('--link', type=str, help='Link diretto al contenuto.')
    parser.add_argument('--seasons', '--s', type=str, default='all')
    parser.add_argument('--episodes', '--e', type=str, default='all')
    parser.add_argument('--outdir', type=str, default=str(Path.cwd() / 'Downloads'))
    parser.add_argument('--headless', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--delay', type=float, default=2.0)
    args = parser.parse_args()

    print(f"{Bcolors.OKCYAN}Verifica della disponibilità di ffmpeg...{Bcolors.ENDC}")
    if not ensure_ffmpeg():
        print(f"\n{Bcolors.FAIL}Errore critico: ffmpeg/ffprobe sono necessari.{Bcolors.ENDC}")
        sys.exit(1)
    print(f"{Bcolors.OKGREEN}ffmpeg è pronto.{Bcolors.ENDC}\n")

    # Inizializzazione di Camoufox in modalità asincrona
    async with AsyncCamoufox(
        headless=args.headless,
        geoip=True,
        humanize=True,
        main_world_eval=True,
        addons=[os.path.abspath(ADDON_PATH)]
    ) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        content_link = args.link
        if not content_link:
            title = input(f"{Bcolors.OKBLUE}Benvenuto! Inserisci il titolo da cercare: {Bcolors.ENDC}")
            results = await search_content(page, title)
            if not results:
                print(f"{Bcolors.FAIL}Nessun risultato per '{title}'.{Bcolors.ENDC}")
                sys.exit()

            print(f"\n{Bcolors.HEADER}--- Risultati della ricerca ---{Bcolors.ENDC}")
            name_w = max(len(r['title']) for r in results)
            type_w = max(len(r['type']) for r in results)
            print(f"{Bcolors.OKCYAN}| {'Idx':<3} | {'Titolo':<{name_w}} | {'Tipo':<{type_w}} |{Bcolors.ENDC}")
            print(f"{Bcolors.HEADER}{'-'*(13+name_w+type_w)}{Bcolors.ENDC}")
            for i, r in enumerate(results):
                color = Bcolors.OKGREEN if r['type'] == "Serie TV" else Bcolors.WARNING
                print(f"{color}| {i+1:<3} | {r['title']:<{name_w}} | {r['type']:<{type_w}} |{Bcolors.ENDC}")
            
            try:
                sel = input(f"{Bcolors.OKBLUE}Scegli un numero (o 'q' per uscire): {Bcolors.ENDC}")
                if sel.lower() == 'q': sys.exit()
                content_link = results[int(sel) - 1]['link']
            except (ValueError, IndexError):
                print(f"{Bcolors.FAIL}Selezione non valida.{Bcolors.ENDC}")
                sys.exit()

        if content_link:
            outdir = Path(args.outdir)
            if "/serietv/" in content_link:
                await enumerate_and_download_series(page, content_link, args.seasons, args.episodes, outdir, args.delay)
            else:
                m3u8 = await get_m3u8_link(page, content_link)
                if m3u8:
                    title = sanitize_filename(await get_page_title(page))
                    movie_dir = outdir / "Film" / title
                    ensure_dir(movie_dir)
                    download_m3u8_to_mp4(m3u8, movie_dir / f"{title}.mp4")
                else:
                    print(f"{Bcolors.FAIL}Impossibile estrarre il link M3U8 per il film.{Bcolors.ENDC}")
    
    print(f"\n{Bcolors.OKGREEN}--- Fine del programma ---{Bcolors.ENDC}")

if __name__ == "__main__":
    # Esegui la funzione main asincrona
    asyncio.run(main())