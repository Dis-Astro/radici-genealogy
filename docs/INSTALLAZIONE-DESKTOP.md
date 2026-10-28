# Radici Desktop 5.0

La versione desktop apre l'interfaccia in una finestra Windows dedicata con Microsoft WebView2. Il servizio genealogico resta un processo indipendente basato su Gramps 6.0.8, accessibile soltanto sulla macchina locale. Non viene aperta una scheda nel browser esterno e non occorre una password per l'accesso dal programma.

## Installazione

Aprire `Installa-Radici-Desktop.exe`. Richiede Windows 10 o 11 a 64 bit, .NET Framework 4.6.2 o successivo e almeno 1,8 GB liberi durante l'installazione. Il pacchetto comprende l'installatore offline Microsoft WebView2; non viene avviato se è già disponibile un runtime compatibile. Il runtime mantiene i propri aggiornamenti di sicurezza.

Programma e dati hanno cartelle distinte nel profilo Windows:

- Programma: `%LOCALAPPDATA%\Programs\Radici`, con versioni in sottocartelle separate.
- Alberi, foto, stampe e backup: `%LOCALAPPDATA%\Radici\Archivio`.
- Interfaccia WebView2: `%LOCALAPPDATA%\Radici\Interfaccia`.

La prima installazione può copiare gli archivi da una chiavetta Radici chiusa. Copia e verifica Dati, Foto, Stampe e Backup, senza formattare né modificare l'originale. Un archivio già presente sul PC non viene sostituito automaticamente. Gli aggiornamenti conservano le versioni precedenti del programma e i dati separati.

Si avvia Radici dal desktop o dal menu Start. «Chiudi e salva» termina il motore dopo la chiusura del database. Un problema di caricamento produce un messaggio con accesso ai registri; trascorsi 90 secondi, l'interfaccia consente di riprovare senza terminare forzatamente il database. L'applicazione utilizza un'unica finestra WebView2 e verifica solo i componenti essenziali all'avvio. I file installati vengono verificati con SHA-256 durante l'estrazione, senza una seconda lettura di tutte le librerie.

La voce «Disinstalla Radici» rimuove il programma e i collegamenti; conserva l'archivio nel profilo. Per trasferire il lavoro, utilizzare esportazioni Gramps o copie complete di sicurezza. Non è ancora presente una sincronizzazione automatica fra PC e chiavetta.

## Diagnostica e limiti

La copia della chiavetta esaminata il 27 ottobre 2026 era priva di `Radici.exe` e `Programma\RadiciMotore.exe`. I dati erano presenti; l'assenza dei due eseguibili impedisce l'avvio. Non è stato possibile stabilire dai registri disponibili chi abbia rimosso i file.

Il collaudo in cartella isolata ha completato l'installazione e l'importazione dei quattro alberi. I 143 test nativi genealogici e i controlli di sicurezza dell'installatore sono stati eseguiti separatamente. Windows ha rifiutato l'esecuzione dei nuovi eseguibili della copia installata con «Accesso negato». Il PC dispone di WatchGuard Endpoint Security 360. Il blocco non è stato attribuito con certezza al prodotto: occorre una verifica della classificazione da parte dell'amministratore. Non sono state modificate o escluse protezioni. Finché l'esecuzione è negata, l'avvio completo della finestra desktop non è certificato su questo PC né sul PC meno potente dell'utente.

Le funzioni dell'album 150 x 100 mm sono incluse: mappa iniziale, indice, schede di famiglia con nomi da almeno 12 punti, rimandi e continuazioni. PDF e pagine SVG vengono generati in modo indipendente dalle posizioni salvate. La mappa serve a orientarsi; la lettura dei nomi avviene nelle schede.

I sorgenti della finestra desktop, dell'installatore e del disinstallatore sono MIT. Motore Gramps e adattatore genealogico mantengono le proprie licenze GPL. Le licenze dei componenti e i sorgenti sono inclusi nel pacchetto; Microsoft WebView2 conserva i termini Microsoft.
