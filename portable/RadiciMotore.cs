using System;using System.IO;using System.Text;using System.Runtime.InteropServices;using System.Diagnostics;
class RadiciMotore {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr LoadLibrary(string p);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr h,string n);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern bool SetDllDirectory(string p);
 [DllImport("kernel32.dll")]static extern uint SetErrorMode(uint flags);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void SetWide(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void Init();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Run(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Finish();
 static string Quote(string p){return "'"+p.Replace("\\","\\\\").Replace("'","\\'")+"'";}
 static int Main(string[] args){
  SetErrorMode(3);string root=args.Length>0?Path.GetFullPath(args[0]):Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,".."));FileStream fileLock=null;
  try{
   bool desktop=Array.IndexOf(args,"--desktop")>=0;
   string program=desktop?AppDomain.CurrentDomain.BaseDirectory:Path.Combine(root,"Programma");
   Process.GetCurrentProcess().PriorityClass=desktop?ProcessPriorityClass.Normal:ProcessPriorityClass.BelowNormal;
   foreach(string folder in new[]{"Dati","Foto","Backup","Stampe","Impostazioni","Temp","Registri"})Directory.CreateDirectory(Path.Combine(root,folder));
   try{fileLock=new FileStream(Path.Combine(root,"Impostazioni/radici.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);}catch(IOException){return 10;}
   Directory.SetCurrentDirectory(root);
   Environment.SetEnvironmentVariable("RADICI_PORTABLE_ROOT",root);Environment.SetEnvironmentVariable("PYTHONNOUSERSITE","1");Environment.SetEnvironmentVariable("PYTHONDONTWRITEBYTECODE","1");
   Environment.SetEnvironmentVariable("RADICI_PROGRAM_ROOT",program);Environment.SetEnvironmentVariable("RADICI_DESKTOP",desktop?"1":null);
   Environment.SetEnvironmentVariable("OMP_NUM_THREADS","1");Environment.SetEnvironmentVariable("OPENBLAS_NUM_THREADS","1");
   int test=Array.IndexOf(args,"--test");if(test>=0&&args.Length>test+1)Environment.SetEnvironmentVariable("RADICI_TEST_SCRIPT",Path.GetFullPath(args[test+1]));else Environment.SetEnvironmentVariable("RADICI_TEST_SCRIPT",null);
   foreach(string name in new[]{"chiudi.flag","backup.flag","pronto.txt"}){string p=Path.Combine(root,"Impostazioni",name);if(File.Exists(p))File.Delete(p);}
   string runtime=Path.Combine(program,"Runtime");Environment.SetEnvironmentVariable("PATH",runtime+";"+Path.Combine(runtime,"lib")+";"+Environment.GetEnvironmentVariable("PATH"));SetDllDirectory(runtime);
   IntPtr h=LoadLibrary(Path.Combine(runtime,"libpython3.14.dll"));if(h==IntPtr.Zero)throw new Exception("DLL non caricata: "+Marshal.GetLastWin32Error());
   var set=(SetWide)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h,"Py_SetPath"),typeof(SetWide));IntPtr path=Marshal.StringToHGlobalUni(Path.Combine(runtime,"lib/library.zip")+";"+Path.Combine(runtime,"lib")+";"+runtime);set(path);
   ((Init)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h,"Py_Initialize"),typeof(Init)))();
   byte[] bytes=Encoding.UTF8.GetBytes("import runpy;runpy.run_path("+Quote(Path.Combine(program,"portable_bootstrap.py"))+",run_name='__main__')\0");IntPtr text=Marshal.AllocHGlobal(bytes.Length);Marshal.Copy(bytes,0,text,bytes.Length);
   int code=((Run)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h,"PyRun_SimpleString"),typeof(Run)))(text);Marshal.FreeHGlobal(text);
   Stopwatch finishTime=Stopwatch.StartNew();
   int finalCode=((Finish)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h,"Py_FinalizeEx"),typeof(Finish)))();
   Marshal.FreeHGlobal(path);
   File.AppendAllText(Path.Combine(root,"Registri/avvio.log"),DateTime.Now.ToString("s")+" Pulizia finale motore: "+finishTime.Elapsed.TotalSeconds.ToString("0.000",System.Globalization.CultureInfo.InvariantCulture)+" s"+Environment.NewLine);
   return code==0&&finalCode==0?0:1;
  }catch(Exception ex){try{File.AppendAllText(Path.Combine(root,"Registri/avvio.log"),DateTime.Now.ToString("s")+" "+ex+Environment.NewLine);}catch{}return 1;}
  finally{if(fileLock!=null)fileLock.Dispose();}
 }
}
