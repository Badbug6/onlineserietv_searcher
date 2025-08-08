## onlineserietv_searcher

Script Python per cercare, aprire e scaricare flussi video (.m3u8) da pagine di film e serie TV su onlineserietv.com. Per le serie TV, il tool individua stagioni ed episodi dalla pagina di selezione interna (iframe) e automatizza l’estrazione del link .m3u8 dal player, salvando infine il video in MP4 con una barra di avanzamento e tempo stimato alla fine.

### Caratteristiche principali
- Rilevamento automatico di film vs serie TV dal link.
- Per le serie: lettura delle stagioni da `div.div_seasons` e degli episodi da `div.div_episodes` all’interno dell’iframe `streaming-serie-tv`.
- Per ogni episodio: selezione del player "fx" (Flexy) quando presente e rilevamento dell’iframe annidato del player.
- Estrazione del link `.m3u8` decodificando lo script offuscato del player.
- Download MP4 tramite `ffmpeg` in copia diretta (senza ricodifica) con barra di avanzamento ed ETA grazie a `tqdm` e una stima di durata via `ffprobe`.
- Nomi file ripuliti automaticamente e struttura di output personalizzabile.

## Requisiti
- Python 3.10+ (raccomandato)
- Google Chrome (il driver è gestito automaticamente da SeleniumBase in modalità Undetected)
- `ffmpeg` e `ffprobe` disponibili nel PATH
  - Su Windows: installa `ffmpeg` da `https://ffmpeg.org` oppure tramite `choco install ffmpeg` se usi Chocolatey
- Dipendenze Python (vedi `requirements.txt`):
  - seleniumbase
  - bs4
  - curl_cffi
  - jsbeautifier
  - tqdm
  - requests

## Installazione
1. Crea/attiva un virtualenv (consigliato):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/macOS
   ```
2. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
3. Assicurati che `ffmpeg` e `ffprobe` siano raggiungibili da terminale:
   ```bash
   ffmpeg -version
   ffprobe -version
   ```

## Uso rapido
- Film singolo (passando il link):
  ```bash
  python main.py --link "https://onlineserietv.com/film/…"
  ```
- Serie TV (tutte le stagioni/episodi):
  ```bash
  python main.py --link "https://onlineserietv.com/serietv/nome-serie/" --seasons all --episodes all
  ```
- Mostra il browser (per debug o se Cloudflare crea problemi):
  ```bash
  python main.py --link "…" --no-headless
  ```

## Opzioni principali
- `--link` (string): URL della pagina di film o serie TV su onlineserietv.com.
- `--seasons` (string, default `all`): per selezionare le stagioni. Esempi: `all`, `1`, `1,3-4`.
- `--episodes` (string, default `all`): per selezionare gli episodi. Esempi: `all`, `1-3,5`.
- `--outdir` (string): cartella base di output (default `Video`).
  - Struttura generata automaticamente:
    - Serie: `Video/Serie/<Nome Serie>/Sxx/<Nome Serie> - Stagione xx - Episodio yy.mp4`
    - Film: `Video/Movie/<Nome Film>/<Nome Film>.mp4`
- `--headless` / `--no-headless`: esegue il browser senza/with GUI (default headless).
- `--max-retries` (int, default 3): tentativi massimi per l’estrazione del link `.m3u8` dal player.
- `--delay` (float, default 2.0): ritardo tra i download degli episodi (aiuta a evitare rate-limit).

Nota: il colore della barra di avanzamento è configurabile nel codice tramite la variabile `PROGRESS_BAR_COLOR` in `main.py`.

## Esempi
- Scaricare tutte le stagioni/episodi di una serie in GUI visibile:
  ```bash
  python main.py --link "https://onlineserietv.com/serietv/black-mirror/" --seasons all --episodes all --outdir Download --no-headless
  ```
- Solo Stagione 2, episodi 1–3 e 6:
  ```bash
  python main.py --link "https://onlineserietv.com/serietv/…" --seasons 2 --episodes 1-3,6
  ```

## Come funziona (alto livello)
1. Apertura pagina contenuto (film/serie) con SeleniumBase in modalità UC (bypass Cloudflare).
2. Serie TV: individuazione dell’iframe `streaming-serie-tv`; dentro l’iframe si leggono
   - le stagioni da `div.div_seasons a` (link del tipo `/streaming-serie-tv/<id>/<season>/<episode>/`),
   - e gli episodi da `div.div_episodes a` nelle relative pagine di stagione.
3. Episodio: selezione del player "fx" (Flexy) quando presente e attesa dell’iframe annidato del player (pattern come `uprot.net/fxe`/`flexy`).
4. Estrazione `.m3u8`: lo script offuscato nel player viene “beautificato” con `jsbeautifier` e si legge il valore `sources[0].src` via regex.
5. Download: si stima la durata con `ffprobe` (se possibile) e si scarica con `ffmpeg -c copy` mostrando una barra `tqdm` in secondi con ETA; in caso contrario, si procede senza barra.
6. Output: salvataggio MP4 con nome ripulito nella struttura `Video/Serie/...` o `Video/Movie/...` come sopra.

## Struttura dei file di output

- Puoi scegliere la cartella di destinazione dei file scaricati usando il parametro `--outdir`.  
  Ad esempio, per salvare tutto nella cartella `Download`, aggiungi `--outdir Download` al comando:
  ```bash
  python main.py --link "..." --outdir Download
  ```
  Se non specifichi `--outdir`, verrà usata la cartella predefinita `Video`.

- La struttura delle cartelle viene creata automaticamente in base al tipo di contenuto:
  - **Serie TV:**  
    `Video/Serie/<Nome Serie>/Sxx/<Nome Serie> - Stagione xx - Episodio yy.mp4`
  - **Film:**  
    `Video/Movie/<Nome Film>/<Nome Film>.mp4`
  (Se usi un valore diverso per `--outdir`, la struttura partirà da quella cartella.)

- I nomi di cartelle e file sono ripuliti da caratteri non validi e spazi superflui per garantire compatibilità e ordine.

## Risoluzione dei problemi
- "Cloudflare / Just a moment": riprova con `--no-headless` e attendi il caricamento della pagina; eventuali ritardi sono normali.
- Nessuna stagione/episodio rilevato: il sito potrebbe avere cambiato markup; i selettori sono in `enumerate_and_download_series` (ricerca di stagioni/episodi) e nella lista dei candidati iframe del player.
- Nessuna barra di avanzamento: se `ffprobe` non riesce a determinare la durata, la barra a tempo non viene mostrata e si usa il fallback senza barra.
- `ffmpeg`/`ffprobe` non trovati: assicurati che siano installati e presenti nel PATH.

## Note legali
Questo progetto è a solo scopo didattico. Devi rispettare i termini d’uso del sito sorgente e le leggi sul diritto d’autore del tuo Paese. L’autore non è responsabile per usi impropri dello strumento.


## Ringraziamenti

- Un sentito grazie a [Arrowar](https://github.com/Arrowar) per il suo repository [Streamincommunity](https://github.com/Arrowar/Streamincommunity), fonte di ispirazione e riferimento per la gestione di player e scraping.
- Grazie anche a [UrloMythus](https://github.com/UrloMythus/MammaMia) per il suo script dedicato all’estrazione dei link dal player Flexy, che ha fornito spunti tecnici fondamentali per la decodifica degli script offuscati.

