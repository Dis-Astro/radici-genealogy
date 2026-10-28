// MIT. Copies a closed archive to an empty destination; never changes the source.
using System;using System.IO;using System.Collections.Generic;using System.Web.Script.Serialization;using System.Security.Cryptography;using System.Runtime.InteropServices;using System.Text;
static class ArchiveImport {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern int GetCurrentPackageFullName(ref uint length,StringBuilder name);
 public static string PackageIdentity(){uint length=0;if(GetCurrentPackageFullName(ref length,null)!=122)return "";var value=new StringBuilder((int)length);return GetCurrentPackageFullName(ref length,value)==0?value.ToString():"";}
 static string Full(string path){return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);}
 static bool Inside(string path,string root){return Full(path).StartsWith(Full(root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
 static void NoLinks(string path){for(string current=Path.GetFullPath(path);current!=null;current=Path.GetDirectoryName(current))if((File.Exists(current)||Directory.Exists(current))&&(File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)throw new IOException("La cartella contiene un collegamento speciale.");}
 static string Hash(string path){using(var stream=File.OpenRead(path))using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(stream));}
 static void CopyFolder(string source,string destination,Action<string> status,Func<bool> cancel){
  if(cancel())throw new OperationCanceledException();NoLinks(source);Directory.CreateDirectory(destination);
  foreach(string path in Directory.GetFiles(source)){
   if(cancel())throw new OperationCanceledException();NoLinks(path);string target=Path.Combine(destination,Path.GetFileName(path));status("Copio e verifico: "+Path.GetFileName(path));
   string sourceHash;using(var input=File.OpenRead(path))using(var output=new FileStream(target,FileMode.CreateNew,FileAccess.Write,FileShare.None))using(var sha=SHA256.Create()){var buffer=new byte[65536];int count;while((count=input.Read(buffer,0,buffer.Length))>0){if(cancel())throw new OperationCanceledException();output.Write(buffer,0,count);sha.TransformBlock(buffer,0,count,buffer,0);}sha.TransformFinalBlock(new byte[0],0,0);sourceHash=BitConverter.ToString(sha.Hash);}
   if(sourceHash!=Hash(target))throw new IOException("La verifica della copia non è riuscita.");
  }
  foreach(string path in Directory.GetDirectories(source))CopyFolder(path,Path.Combine(destination,Path.GetFileName(path)),status,cancel);
 }
 public static string FindUsb(){foreach(DriveInfo drive in DriveInfo.GetDrives())try{if((drive.DriveType!=DriveType.Fixed&&drive.DriveType!=DriveType.Removable)||!drive.IsReady)continue;string root=Path.Combine(drive.RootDirectory.FullName,"Radici");if(File.Exists(Path.Combine(root,"Dati/trees.json")))return root;}catch{}return "";}
 public static bool Copy(string source,string destination,Action<string> status,Func<bool> cancel){
  if(File.Exists(Path.Combine(destination,"Dati/trees.json")))return false;
  source=Full(source);destination=Full(destination);NoLinks(source);NoLinks(destination);
  if(source.Equals(destination,StringComparison.OrdinalIgnoreCase)||Inside(source,destination)||Inside(destination,source))throw new IOException("Origine e destinazione devono essere cartelle distinte.");
  if(Directory.Exists(destination)&&Directory.GetFileSystemEntries(destination).Length>0)throw new IOException("La destinazione non è vuota. Nessun file viene sostituito.");
  string index=Path.Combine(source,"Dati/trees.json");if(!File.Exists(index))throw new IOException("Scegli la cartella Radici che contiene Dati e Foto.");
  var json=new JavaScriptSerializer{MaxJsonLength=8*1024*1024};var catalog=json.DeserializeObject(File.ReadAllText(index)) as Dictionary<string,object>;
  if(catalog==null||!catalog.ContainsKey("trees")||!catalog.ContainsKey("active"))throw new IOException("Indice degli alberi non valido.");
  var trees=catalog["trees"] as object[];if(trees==null||trees.Length==0)throw new IOException("Non ci sono alberi da copiare.");bool active=false;
  foreach(object item in trees){var row=item as Dictionary<string,object>;string id=row!=null&&row.ContainsKey("id")?Convert.ToString(row["id"]):"";if(!System.Text.RegularExpressions.Regex.IsMatch(id,"^[a-zA-Z0-9_-]{1,80}$"))throw new IOException("Identificativo non valido.");if(id==Convert.ToString(catalog["active"]))active=true;string path=id=="original"?Path.Combine(source,"Dati/tree/sqlite.db"):Path.Combine(source,"Dati/trees",id,"tree/sqlite.db");if(!File.Exists(path))throw new IOException("Un archivio della chiavetta è incompleto.");}
  if(!active)throw new IOException("L’albero attivo non esiste.");
  string parent=Path.GetDirectoryName(destination);Directory.CreateDirectory(parent);string stage=Path.Combine(parent,".radici-stage-first-use-"+Guid.NewGuid().ToString("N"));FileStream sourceLock=null;
  try{
   string lockPath=Path.Combine(source,"Impostazioni/radici.lock");if(File.Exists(lockPath))sourceLock=new FileStream(lockPath,FileMode.Open,FileAccess.Read,FileShare.None);
   Directory.CreateDirectory(stage);foreach(string folder in new[]{"Dati","Foto","Stampe","Backup"})if(Directory.Exists(Path.Combine(source,folder)))CopyFolder(Path.Combine(source,folder),Path.Combine(stage,folder),status,cancel);
   if(cancel())throw new OperationCanceledException();
   if(Directory.Exists(destination)){if(Directory.GetFileSystemEntries(destination).Length>0)throw new IOException("La destinazione è cambiata durante la copia.");Directory.Delete(destination);}
   Directory.Move(stage,destination);return true;
  }finally{
   if(sourceLock!=null)sourceLock.Dispose();
   // Stage is created here from a checked parent and never points at either archive.
   if(Inside(stage,parent)&&Path.GetFileName(stage).StartsWith(".radici-stage-first-use-",StringComparison.Ordinal)&&Directory.Exists(stage)){NoLinks(stage);Directory.Delete(stage,true);}
  }
 }
}
