# Microsoft Store / MSIX

La distribuzione gratuita prevista è **Microsoft Store con pacchetto MSIX**. Il codice rimane GPL/MIT secondo i singoli componenti. Il programma non richiede SignPath e non acquista certificati. La certificazione Microsoft è un passaggio distinto dalla build e dai test.

## Identità dell'editore

La pubblicazione è prevista come sviluppatore individuale. Il titolare deve accedere da https://storedeveloper.microsoft.com/ e completare direttamente la verifica dell'identità e l'accordo sviluppatore. La creazione del pacchetto non equivale alla pubblicazione.

Dopo aver prenotato il nome dell'app, da Partner Center → app → Product identity copiare **esattamente** Package/Identity/Name, Package/Identity/Publisher, Package/Properties/PublisherDisplayName e il nome prenotato. Usare `identity.example.json` come modello. Il builder rifiuta valori vuoti, segnaposto e l'identità di sviluppo quando viene richiesto un pacchetto per lo Store.

Variabili GitHub Actions (valori pubblici, non password):

| Variabile | Valore da Partner Center |
|---|---|
| `STORE_IDENTITY_NAME` | Package/Identity/Name |
| `STORE_PUBLISHER` | Package/Identity/Publisher completo, incluso `CN=` |
| `STORE_PUBLISHER_DISPLAY_NAME` | Package/Properties/PublisherDisplayName |
| `STORE_DISPLAY_NAME` | Nome prenotato dell'app |

Avviare manualmente **Windows desktop** con `store_package=true` e `sign=false`. L'artifact `radici-msix-result` conterrà il `.msixupload` da sottoporre alla certificazione Microsoft. Il pacchetto è intenzionalmente non firmato: lo Store applica la firma alla versione distribuita dopo i propri controlli. La versione di sviluppo `BOZZA-NON-INSTALLABILE` non deve essere inviata allo Store.

## Build locale

Richiede una build Windows già preparata tramite `scripts/build_windows.py`, più MakeAppx dal Windows SDK ufficiale:

```powershell
python scripts/build_windows.py prepare
python scripts/build_windows.py binaries
python scripts/build_windows.py test
python scripts/build_msix.py --development
python scripts/build_msix.py --store-identity .build/identity.json
```

Le due ultime righe sono alternative; usare una cartella di staging pulita per ogni build. Il builder non cancella automaticamente una cartella preesistente e non usa `/nv`: la validazione MakeAppx rimane abilitata. Il `.msixupload` è un archivio del solo pacchetto MSIX; i simboli diagnostici sono facoltativi e non sono attualmente inclusi.

## Dati e disinstallazione

Programma e motore sono installati nella cartella gestita da Windows; tutti i dati genealogici restano in `%LOCALAPPDATA%\Radici\Archivio`. Il pacchetto richiede le capability `runFullTrust` e `unvirtualizedResources`, con motivazione in `CERTIFICATION.md`.

Su Windows 11 la sola cartella dell'archivio è esclusa dalla virtualizzazione. Su Windows 10 2004 o successivo viene usato il meccanismo compatibile `FileSystemWriteVirtualization=disabled`. Le scritture del registro rimangono virtualizzate. Questo permette di ritrovare gli archivi della precedente versione desktop e conservarli dopo la disinstallazione; deve essere verificato tramite il test di installazione/rimozione e approvato dallo Store.

Al primo avvio MSIX, se non esiste un archivio sul PC, una procedura chiede se copiare gli alberi da una chiavetta chiusa. Copia Dati, Foto, Stampe e Backup in una cartella temporanea, verifica gli hash e pubblica la nuova copia solo a fine operazione. Un archivio già presente non viene sostituito. L'originale non è cancellato né modificato. Annullare chiudendo la finestra interrompe la sola copia incompleta.

## Componente grafico

Il pacchetto usa Microsoft WebView2 Evergreen condiviso, preinstallato su Windows 11 e sulla maggioranza dei Windows 10 aggiornati. Non contiene un secondo browser né esegue automaticamente altri installatori. Se il runtime manca o è troppo vecchio, mostra un pulsante per aprire il download ufficiale Microsoft e riprovare dopo l'installazione. Questo prerequisito è dichiarato nella scheda e nelle note di certificazione.

## Verifica e firma di prova

La CI esegue i test del vero motore Gramps e quelli del manifesto/payload. `Test-Msix.ps1` è vincolato ai runner Windows temporanei ospitati da GitHub: installa una copia di sviluppo, apre la finestra con la vera identità di pacchetto, verifica WebView2, chiude in modo ordinato, rimuove il programma e controlla che il catalogo sintetico resti disponibile.

Per tale prova viene creato un certificato temporaneo **solo nella VM CI**, con chiave non esportabile. A fine test vengono rimossi il certificato e il relativo trust. Nessun certificato viene creato o reso attendibile sul computer dell'utente e nessuna protezione antivirus viene esclusa. Questa firma di prova non è una firma Microsoft Store e non viene pubblicata come release.

Una firma autofirmata può essere usata per collaudi privati solo sui computer che la considerano espressamente attendibile. Non fornisce una firma riconosciuta su PC generici e non garantisce l'autorizzazione dell'endpoint security.

## Stato e limiti

La bozza può essere costruita prima che esista un account sviluppatore. La versione pubblicabile richiede l'identità reale e la verifica finale in Partner Center. La certificazione Store, l'approvazione delle capability, la verifica d'identità e il collaudo sul PC meno potente sono passaggi separati; non vengono dichiarati superati dalla sola creazione del file.

Riferimenti: [MakeAppx](https://learn.microsoft.com/windows/msix/package/create-app-package-with-makeappx-tool), [virtualizzazione](https://learn.microsoft.com/windows/msix/desktop/flexible-virtualization), [firma MSIX](https://learn.microsoft.com/windows/msix/package/sign-msix-package-guide), [WebView2](https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution).
