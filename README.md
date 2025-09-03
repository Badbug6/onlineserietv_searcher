Script Python per cercare e scaricare flussi video (.m3u8) da pagine di film e serie TV su onlineserietv.com.
Lo script è **autonomo e portatile**: gestisce automaticamente il download del browser necessario per l'automazione e può scaricare FFmpeg se non è già installato.

### Caratteristiche principali
- **Navigazione Robusta:** Utilizza **Camoufox (basato su Playwright)** per una navigazione più affidabile, eludendo le comuni protezioni anti-bot.
- **Gestione FFmpeg:** Se `ffmpeg` non è nel PATH, lo script tenta di scaricare una versione compatibile per il tuo sistema operativo.
- **Logica di Download Intelligente:**
    - Rileva automaticamente film e serie TV.
    - Per le serie, legge stagioni ed episodi dall'interfaccia del sito.
    - Seleziona in modo intelligente il player video corretto (`Flexy`) per evitare CAPTCHA.
    - Simula le interazioni umane, come cliccare sul pulsante "Play" per attivare il caricamento del video.
    - Include una logica di **tentativi multipli** per superare caricamenti lenti o errori temporanei.
- **Download Ottimizzato:** Scarica i video in formato MP4 tramite `ffmpeg` (copia diretta, senza ricodifica) e mostra una barra di avanzamento con il tempo trascorso.
- **Output Organizzato:** Salva i file con nomi puliti in una struttura di cartelle logica e personalizzabile.

## Requisiti
- Python 3.10+
- `ffmpeg` e `ffprobe` (consigliato, ma lo script tenterà di installarli se non presenti)
- Dipendenze Python (installate automaticamente tramite `requirements.txt`)

## Installazione
1.  **Clona il repository (o scarica lo ZIP):**
    ```bash
    git clone https://github.com/tuo-username/onlineserietv_searcher.git
    cd onlineserietv_searcher
    ```
2.  **Crea e attiva un ambiente virtuale (consigliato):**
    ```bash
    python -m venv .venv
    # Su Windows
    .venv\Scripts\activate
    # Su Linux/macOS
    source .venv/bin/activate
    ```
3.  **Installa le dipendenze Python:**
    ```bash
    pip install -r requirements.txt
    ```

### Prima Esecuzione
La prima volta che avvii lo script, questo eseguirà una configurazione automatica:
- **Controllerà la presenza del browser** per l'automazione.
- Se non lo trova, avvierà il **download automatico** (potrebbe richiedere qualche minuto). Vedrai uno **spinner di attività** che indica che il processo è in corso.
- Le esecuzioni successive saranno immediate.

## Uso
Lo script può essere usato in due modalità: **ricerca interattiva** o **download diretto** tramite link.

**Esempio 1: Ricerca Interattiva**
Esegui lo script senza argomenti. Ti verrà chiesto di inserire un titolo, e potrai scegliere dai risultati.
```bash
python main.py
```

**Esempio 2: Download Diretto di un Film**
```bash
python main.py --link "https://onlineserietv.com/film/nome-film/"
```

**Esempio 3: Download di una Serie TV Completa**
```bash
python main.py --link "https://onlineserietv.com/serietv/nome-serie/"
```

**Esempio 4: Download di Episodi Specifici**
Scarica la stagione 2, episodi da 1 a 3 e l'episodio 5.
```bash
python main.py --link "https://onlineserietv.com/serietv/nome-serie/" --seasons 2 --episodes 1-3,5
```

## Opzioni Principali
- `--link` (string): URL diretto della pagina del film o della serie. Se omesso, avvia la modalità interattiva.
- `--seasons` (string, default `all`): Seleziona le stagioni da scaricare. Esempi: `all`, `1`, `1,3-4`.
- `--episodes` (string, default `all`): Seleziona gli episodi. Esempi: `all`, `1-3,5`.
- `--outdir` (string): Cartella base per i download (default: `Downloads`).
- `--headless` / `--no-headless`: Esegue il browser in background (default) o in modalità visibile (utile per il debug).
- `--delay` (float, default `2.0`): Secondi di attesa tra il download di un episodio e il successivo.

## Come Funziona (dettagli tecnici)
1.  **Setup:** Alla prima esecuzione, lo script invoca `playwright install` per scaricare un'istanza locale del browser nella cartella `browser_data`.
2.  **Navigazione:** La pagina viene aperta con **Camoufox**, che gestisce l'identità del browser per ridurre le probabilità di essere bloccati.
3.  **Logica di Estrazione:**
    - Per le serie, viene individuato l'iframe `streaming-serie-tv` per enumerare stagioni ed episodi.
    - Per ogni episodio, lo script **controlla il player attivo**. Se non è "Flexy (`fx`)", lo seleziona e attende il ricaricamento della pagina.
    - Viene eseguito un controllo proattivo per la presenza di **CAPTCHA**; se rilevato, lo script forza un nuovo tentativo.
    - Viene simulato un click sull'area del player (`.video-js`) per attivare la richiesta del flusso video.
4.  **Parsing:** Lo script offuscato all'interno dell'iframe del player viene analizzato con `jsbeautifier` e una regex per estrarre il link `.m3u8` finale.
5.  **Download:** `ffmpeg` viene usato per scaricare il flusso video senza ricodifica (`-c copy`), garantendo la massima qualità e velocità.

## Struttura dei File di Output
I file vengono salvati in una struttura ordinata all'interno della cartella specificata con `--outdir` (o `Downloads` di default).
-   **Serie TV:**  
    `Downloads/Serie/<Nome Serie>/Sxx/<Nome Serie> - SxxExx.mp4`
-   **Film:**  
    `Downloads/Film/<Nome Film>/<Nome Film>.mp4`

## Risoluzione dei Problemi
-   **Bloccato su "Just a moment..." o CAPTCHA:** Lo script è progettato per gestire queste situazioni con tentativi multipli. Se il problema persiste, prova ad eseguirlo con `--no-headless` per vedere cosa sta succedendo nel browser.
-   **Installazione del browser fallita:** Assicurati di avere una connessione a internet stabile e che nessun firewall stia bloccando il download. Puoi provare a cancellare la cartella `browser_data` e riavviare lo script.
-   **FFmpeg non trovato:** Se il download automatico fallisce, installa `ffmpeg` manualmente e assicurati che sia accessibile dal tuo terminale.

## Note Legali
Questo progetto è stato creato a solo scopo didattico. L'utente è tenuto a rispettare i termini di utilizzo del sito sorgente e le leggi sul diritto d'autore vigenti nel proprio Paese. L'autore non si assume alcuna responsabilità per un uso improprio dello strumento.

## Ringraziamenti
- Un sentito grazie a [Arrowar](https://github.com/Arrowar) per il suo repository [Streamincommunity](https://github.com/Arrowar/Streamincommunity), fonte di ispirazione e riferimento per la gestione di player e scraping.
- Grazie anche a [UrloMythus](https://github.com/UrloMythus/MammaMia) per il suo script dedicato all’estrazione dei link dal player Flexy, che ha fornito spunti tecnici fondamentali per la decodifica degli script offuscati.