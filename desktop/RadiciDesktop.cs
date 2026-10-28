// MIT licensed desktop host. The independent genealogy service remains GPL-2.0-or-later.
using System;
using System.IO;
using System.Net;
using System.Text;
using System.Drawing;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class RadiciDesktop : Form {
 const string Release="5.0.0";
 readonly string program,archive,smoke;
 readonly Label status=new Label();
 readonly Panel loading=new Panel();
 readonly ProgressBar progress=new ProgressBar();
 readonly Button retry=new Button(),logs=new Button();
 readonly System.Windows.Forms.Timer wakeTimer=new System.Windows.Forms.Timer();
 readonly JavaScriptSerializer json=new JavaScriptSerializer();
 EventWaitHandle wake;
 Process engine;
 WebView2 browser;
 string endpoint,token;
 bool starting,closing,allowClose;
 [DllImport("ntdll.dll",CharSet=CharSet.Unicode)]static extern int RtlGetVersion(ref OSVERSION value);
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]struct OSVERSION {public int Size,Major,Minor,Build,Platform;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=128)]public string ServicePack;}

 static string Option(string[] args,string key,string fallback){int n=Array.IndexOf(args,key);return n>=0&&n+1<args.Length?Path.GetFullPath(args[n+1]):fallback;}
 static string Key(string data){using(var sha=SHA256.Create())return "Local\\RadiciDesktop-"+BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(data.ToUpperInvariant()))).Replace("-","");}
 public static bool Supported(){var version=new OSVERSION{Size=Marshal.SizeOf(typeof(OSVERSION))};return Environment.Is64BitOperatingSystem&&RtlGetVersion(ref version)==0&&version.Major>=10;}
 [STAThread]static int Main(string[] args){
  Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
  if(!Supported()){MessageBox.Show("Radici richiede Windows 10 o 11 a 64 bit. Questo computer non è compatibile con il motore Gramps 6.0.8 incluso.","Radici",MessageBoxButtons.OK,MessageBoxIcon.Information);return 2;}
  string program=AppDomain.CurrentDomain.BaseDirectory;
  string data=Option(args,"--data-root",Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Radici","Archivio"));
  bool first;using(var single=new Mutex(true,Key(data),out first)){
   if(!first){try{using(var existing=EventWaitHandle.OpenExisting(Key(data)+"-Show"))existing.Set();}catch{}return 0;}
   using(var signal=new EventWaitHandle(false,EventResetMode.AutoReset,Key(data)+"-Show"))
   using(var form=new RadiciDesktop(program,data,Option(args,"--smoke-report",null),signal)){Application.Run(form);}
  }
  return 0;
 }
 RadiciDesktop(string folder,string data,string report,EventWaitHandle signal){
  program=folder;archive=data;smoke=report;wake=signal;
  Text="Radici · La storia della tua famiglia";StartPosition=FormStartPosition.CenterScreen;
  Size=new Size(1280,850);MinimumSize=new Size(900,650);Font=new Font("Segoe UI",11);BackColor=Color.FromArgb(246,246,239);
  try{Icon=new Icon(Path.Combine(program,"Radici.ico"));}catch{}
  var bar=new FlowLayoutPanel{Dock=DockStyle.Top,Height=52,Padding=new Padding(10,6,6,4),BackColor=Color.White,WrapContents=false};
  foreach(string title in new[]{"Le mie stampe","Copia di sicurezza","Cartella dei dati"}){
   var button=new Button{Text=title,AutoSize=true,Height=37,FlatStyle=FlatStyle.Flat,Margin=new Padding(3,0,8,0)};button.FlatAppearance.BorderColor=Color.FromArgb(200,210,195);bar.Controls.Add(button);
   if(title=="Le mie stampe")button.Click+=(s,e)=>OpenFolder("Stampe");
   else if(title=="Cartella dei dati")button.Click+=(s,e)=>OpenFolder("");
   else button.Click+=async(s,e)=>{button.Enabled=false;try{await Task.Run(()=>Control("backup"));MessageBox.Show(this,"Copia avviata. Sarà salvata nella cartella Backup del PC.","Radici");}catch(Exception ex){ShowError("Copia non avviata. "+ex.Message);}finally{button.Enabled=true;}};
  }
  var exit=new Button{Text="Chiudi e salva",AutoSize=true,Height=37,Margin=new Padding(12,0,0,0)};exit.Click+=(s,e)=>Close();bar.Controls.Add(exit);
  loading.Dock=DockStyle.Fill;loading.Padding=new Padding(40);loading.BackColor=BackColor;
  var heading=new Label{Text="Radici",Font=new Font("Georgia",32),AutoSize=true,Location=new Point(40,42),ForeColor=Color.FromArgb(38,73,52)};
  status.SetBounds(44,115,760,95);status.AutoEllipsis=false;status.Text="Preparazione dell’archivio…";
  progress.SetBounds(44,218,650,16);progress.Style=ProgressBarStyle.Marquee;progress.MarqueeAnimationSpeed=35;
  retry.SetBounds(44,260,240,44);retry.Text="Riprova l’avvio";retry.Visible=false;retry.Click+=async(s,e)=>await Boot();
  logs.SetBounds(298,260,240,44);logs.Text="Apri il registro";logs.Visible=false;logs.Click+=(s,e)=>OpenFolder("Registri");
  loading.Controls.AddRange(new Control[]{heading,status,progress,retry,logs});Controls.Add(loading);Controls.Add(bar);
  wakeTimer.Interval=400;wakeTimer.Tick+=(s,e)=>{if(wake.WaitOne(0)){Show();WindowState=FormWindowState.Normal;Activate();}};wakeTimer.Start();
  Shown+=async(s,e)=>await Boot();FormClosing+=async(s,e)=>{if(allowClose)return;e.Cancel=true;if(closing)return;await Stop();};
 }
 void Log(string message){try{Directory.CreateDirectory(Path.Combine(archive,"Registri"));File.AppendAllText(Path.Combine(archive,"Registri/desktop.log"),DateTime.Now.ToString("s")+" "+message+Environment.NewLine);}catch{}}
 void OpenFolder(string name){try{string path=Path.Combine(archive,name);Directory.CreateDirectory(path);Process.Start(new ProcessStartInfo(path){UseShellExecute=true});}catch(Exception ex){ShowError(ex.Message);}}
 void ShowError(string message){if(IsDisposed)return;status.Text=message;progress.Style=ProgressBarStyle.Blocks;retry.Visible=logs.Visible=true;loading.Visible=true;loading.BringToFront();Log(message);}
 string Request(string path,string body=null,bool bootstrap=false){
  var req=(HttpWebRequest)WebRequest.Create((bootstrap?endpoint+"/?avvio="+Uri.EscapeDataString(token):endpoint+path));req.Proxy=null;req.Timeout=1500;req.ReadWriteTimeout=1500;req.KeepAlive=false;
  if(!bootstrap)req.Headers["X-Radici-Control"]=token;
  if(body!=null){req.Method="POST";req.ContentType="application/json";byte[] bytes=Encoding.UTF8.GetBytes(body);req.ContentLength=bytes.Length;using(var output=req.GetRequestStream())output.Write(bytes,0,bytes.Length);}
  using(var response=req.GetResponse())using(var input=new StreamReader(response.GetResponseStream()))return input.ReadToEnd();
 }
 void Control(string action){if(endpoint==null)throw new IOException("Il motore non è ancora pronto.");Request("/api/portable/control","{\"action\":\""+action+"\"}");}
 bool ReadAddress(){
  try{var uri=new Uri(File.ReadAllText(Path.Combine(archive,"Impostazioni/pronto.txt")).Trim());if(uri.Scheme!="http"||uri.Host!="127.0.0.1"||!uri.Query.StartsWith("?avvio="))return false;endpoint=uri.GetLeftPart(UriPartial.Authority);token=Uri.UnescapeDataString(uri.Query.Substring(7));return token.Length>=20;}catch{return false;}
 }
 async Task Boot(){
  if(starting||closing)return;starting=true;retry.Visible=logs.Visible=false;progress.Style=ProgressBarStyle.Marquee;loading.Visible=true;loading.BringToFront();
  try{
   foreach(string name in new[]{"Dati","Foto","Stampe","Backup","Registri","Impostazioni","Temp"})Directory.CreateDirectory(Path.Combine(archive,name));
   foreach(string name in new[]{"Programma/RadiciMotore.exe","Programma/Runtime/libpython3.14.dll","Programma/Runtime/lib/library.zip","Programma/app/static/index.html"})if(!File.Exists(Path.Combine(program,name)))throw new IOException("Manca un componente del programma: "+name+". Riapri l’installatore per riparare Radici; gli alberi saranno conservati.");
   string runtime=CoreWebView2Environment.GetAvailableBrowserVersionString();Version runtimeVersion;
   if(!Version.TryParse(runtime.Split(' ')[0],out runtimeVersion)||runtimeVersion.Major<131)throw new IOException("Il componente grafico Microsoft WebView2 richiede un aggiornamento. Riapri l’installatore di Radici.");
   if(engine==null||engine.HasExited){
    if(engine!=null)engine.Dispose();endpoint=token=null;
    engine=Process.Start(new ProcessStartInfo(Path.Combine(program,"Programma/RadiciMotore.exe"),"\""+archive.TrimEnd('\\')+"\" --desktop"){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,WorkingDirectory=archive});
    engine.EnableRaisingEvents=true;engine.Exited+=(s,e)=>{try{BeginInvoke((Action)(()=>{if(!closing)ShowError("Il motore dell’archivio si è fermato. Premi Riprova oppure apri il registro.");}));}catch{}};
   }
   Stopwatch elapsed=Stopwatch.StartNew();bool ready=false;
   while(elapsed.Elapsed.TotalSeconds<90&&!closing){
    if(engine.HasExited)throw new IOException("Il motore si è fermato durante l’avvio (codice "+engine.ExitCode+"). Apri il registro per i dettagli.");
    if(ReadAddress())try{
     var report=json.DeserializeObject(await Task.Run(()=>Request("/api/portable/status"))) as System.Collections.Generic.Dictionary<string,object>;
     if(report!=null){status.Text=(string)report["message"]+Environment.NewLine+"Tempo trascorso: "+(int)elapsed.Elapsed.TotalSeconds+" secondi";if((bool)report["ready"]){ready=true;break;}}
    }catch(WebException){}
    await Task.Delay(350);
   }
   if(closing)return;
   if(!ready)throw new IOException("L’apertura sta richiedendo più di 90 secondi. Il caricamento non viene interrotto: puoi attendere e premere Riprova oppure consultare il registro.");
   status.Text="Apertura della finestra della tua famiglia…";
   if(browser!=null){Controls.Remove(browser);browser.Dispose();browser=null;}
   browser=new WebView2{Dock=DockStyle.Fill,DefaultBackgroundColor=Color.FromArgb(246,246,239)};Controls.Add(browser);browser.BringToFront();
   string profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Radici","Interfaccia");
   var environment=await CoreWebView2Environment.CreateAsync(null,profile,new CoreWebView2EnvironmentOptions("--disable-background-networking --disable-sync"));
   await browser.EnsureCoreWebView2Async(environment);
   browser.CoreWebView2.Settings.AreDevToolsEnabled=false;browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled=false;browser.CoreWebView2.Settings.IsStatusBarEnabled=false;
   browser.CoreWebView2.NewWindowRequested+=(s,e)=>e.Handled=true;
   browser.CoreWebView2.NavigationStarting+=(s,e)=>{Uri uri;if(!Uri.TryCreate(e.Uri,UriKind.Absolute,out uri)||uri.GetLeftPart(UriPartial.Authority)!=endpoint)e.Cancel=true;};
   browser.CoreWebView2.WebMessageReceived+=(s,e)=>{if(e.Source.StartsWith(endpoint+"/",StringComparison.Ordinal)&&e.TryGetWebMessageAsString()=="reconnect")browser.CoreWebView2.Navigate(endpoint+"/?avvio="+Uri.EscapeDataString(token));};
   browser.CoreWebView2.ProcessFailed+=(s,e)=>ShowError("La finestra grafica si è fermata. I dati già salvati sono conservati. Premi Riprova.");
   browser.CoreWebView2.NavigationCompleted+=(s,e)=>{if(e.IsSuccess){loading.Visible=false;Log("Finestra pronta; versione "+Release+"; motore "+engine.Id+"; caricamento "+elapsed.Elapsed.TotalSeconds.ToString("0.0")+" s");if(smoke!=null)File.WriteAllText(smoke,json.Serialize(new{ready=true,version=Release,native_window=true,webview_navigation=true,worker_pid=engine.Id,data_root=archive,seconds=elapsed.Elapsed.TotalSeconds}));}else ShowError("La finestra non è riuscita ad aprire l’archivio. Premi Riprova.");};
   browser.CoreWebView2.Navigate(endpoint+"/?avvio="+Uri.EscapeDataString(token));
  }catch(Exception ex){ShowError("Avvio non completato. "+ex.Message);}
  finally{starting=false;}
 }
 async Task Stop(){
  closing=true;loading.Visible=true;loading.BringToFront();status.Text="Chiusura e salvataggio dell’archivio…";retry.Visible=logs.Visible=false;progress.Style=ProgressBarStyle.Marquee;
  try{
   if(engine!=null&&!engine.HasExited){
    try{if(endpoint==null)ReadAddress();await Task.Run(()=>Control("shutdown"));}catch{File.WriteAllText(Path.Combine(archive,"Impostazioni/chiudi.flag"),"1");}
    bool ended=await Task.Run(()=>engine.WaitForExit(30000));
    if(!ended){ShowError("L’archivio sta completando la chiusura. Attendi e riprova Chiudi e salva; non estrarre dischi mentre il programma salva.");closing=false;return;}
   }
   if(browser!=null){browser.Dispose();browser=null;}wakeTimer.Stop();allowClose=true;Close();
  }catch(Exception ex){closing=false;ShowError("Chiusura non completata: "+ex.Message);}
 }
 protected override void Dispose(bool disposing){if(disposing){wakeTimer.Dispose();if(engine!=null)engine.Dispose();}base.Dispose(disposing);}
}
