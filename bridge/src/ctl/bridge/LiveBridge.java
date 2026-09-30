package ctl.bridge;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.eclipse.core.commands.Command;
import org.eclipse.core.commands.IParameter;
import org.eclipse.core.commands.NotEnabledException;
import org.eclipse.core.commands.NotHandledException;
import org.eclipse.core.commands.Parameterization;
import org.eclipse.core.commands.ParameterizedCommand;
import org.eclipse.core.filesystem.EFS;
import org.eclipse.core.filesystem.IFileStore;
import org.eclipse.core.runtime.IConfigurationElement;
import org.eclipse.core.runtime.Platform;
import org.eclipse.core.runtime.jobs.IJobManager;
import org.eclipse.core.runtime.jobs.Job;
import org.eclipse.e4.core.contexts.IEclipseContext;
import org.eclipse.jface.text.IDocument;
import org.eclipse.swt.widgets.Composite;
import org.eclipse.swt.widgets.Control;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Item;
import org.eclipse.swt.widgets.Menu;
import org.eclipse.swt.widgets.MenuItem;
import org.eclipse.swt.widgets.Shell;
import org.eclipse.swt.widgets.Table;
import org.eclipse.swt.widgets.ToolBar;
import org.eclipse.swt.widgets.ToolItem;
import org.eclipse.swt.widgets.Tree;
import org.eclipse.swt.widgets.Widget;
import org.eclipse.ui.IEditorInput;
import org.eclipse.ui.IEditorPart;
import org.eclipse.ui.IEditorReference;
import org.eclipse.ui.IPerspectiveDescriptor;
import org.eclipse.ui.IViewPart;
import org.eclipse.ui.IViewReference;
import org.eclipse.ui.IWorkbench;
import org.eclipse.ui.IWorkbenchPage;
import org.eclipse.ui.IWorkbenchWindow;
import org.eclipse.ui.PlatformUI;
import org.eclipse.ui.commands.ICommandService;
import org.eclipse.ui.console.ConsolePlugin;
import org.eclipse.ui.console.IConsole;
import org.eclipse.ui.console.IConsoleManager;
import org.eclipse.ui.console.IConsoleView;
import org.eclipse.ui.console.TextConsole;
import org.eclipse.ui.handlers.IHandlerService;
import org.eclipse.ui.ide.FileStoreEditorInput;
import org.eclipse.ui.views.IViewDescriptor;
import org.osgi.framework.Bundle;
import org.osgi.framework.BundleActivator;
import org.osgi.framework.BundleContext;

/**
 * eclipse-ctl bridge: line protocol on 127.0.0.1:&lt;port&gt; (default 8777).
 *
 * <pre>
 * Request : one line, "&lt;method&gt; [argument]"
 * Response: "OK" | "ERR &lt;code&gt; &lt;message&gt;"  then payload lines  then "END"
 * </pre>
 *
 * Error codes (closed set, design.md §3): badrequest | notfound | disabled | unhandled |
 * timeout | noWorkBench | internal | busy.
 *
 * Threading (design.md §4): one thread per connection, at most {@link #MAX_CONNECTIONS}
 * at a time; over that the connection is answered with {@code ERR busy} and closed.
 * {@code ui.*} / {@code cmd.*} run on the SWT event thread via {@code asyncExec} with a
 * bounded wait; {@code sys.*} never touches the UI thread, so it keeps answering while a
 * modal dialog blocks the UI (G3).
 *
 * Method table is single-sourced in {@link #methods}; {@code sys.help} introspects it.
 */
public class LiveBridge implements BundleActivator {

    // ------------------------------------------------------------- constants

    /** Wire protocol version; independent of the bundle version (design-project.md §15.2). */
    static final int PROTOCOL_VERSION = 1;

    private static final int DEFAULT_PORT = 8777;
    /** Max simultaneously served connections (design.md §4). */
    private static final int MAX_CONNECTIONS = 8;
    /** Bounded wait for a UI-dispatched task (design.md §3, §17.5). */
    private static final int DEFAULT_UI_TIMEOUT_MS = 15000;
    /** Budget of {@code sys.wait jobs-idle} when no explicit millisecond argument is given. */
    private static final long DEFAULT_JOBS_IDLE_WAIT_MS = 15000L;
    private static final long SOCKET_READ_TIMEOUT_MS = 60000L;
    private static final int CONSOLE_TAIL_DEFAULT = 50;
    private static final int CONSOLE_MAX_CHARS = 200000;
    private static final int JOBS_LIST_MAX = 10;
    private static final String CONSOLE_VIEW_ID = "org.eclipse.ui.console.ConsoleView";
    private static final String EP_HANDLERS = "org.eclipse.ui.handlers";

    /** Closed error-code set (design.md §3 / P2.3). */
    private static final String E_BADREQUEST = "badrequest";
    private static final String E_NOTFOUND = "notfound";
    private static final String E_DISABLED = "disabled";
    private static final String E_UNHANDLED = "unhandled";
    private static final String E_TIMEOUT = "timeout";
    private static final String E_NO_WORKBENCH = "noWorkbench";
    private static final String E_INTERNAL = "internal";
    private static final String E_BUSY = "busy";
    private static final String CODES =
            E_BADREQUEST + "," + E_NOTFOUND + "," + E_DISABLED + "," + E_UNHANDLED + ","
            + E_TIMEOUT + "," + E_NO_WORKBENCH + "," + E_INTERNAL + "," + E_BUSY;

    /**
     * Bridge port. Resolution order (frozen contract):
     *   1. {@code -Dctl.port=<n>}   2. environment {@code CTL_PORT}   3. 8777
     */
    private static final int PORT = resolvePort();
    /**
     * Log file. Resolution order (frozen contract):
     *   1. {@code -Dctl.log=<path>}   2. environment {@code CTL_LOG}
     *   3. {@code <user.home>/.eclipse-ctl/bridge.log}
     */
    private static final String LOG_PATH = resolveLogPath();

    private static int resolvePort() {
        String v = System.getProperty("ctl.port");
        if (v == null || v.trim().isEmpty()) v = System.getenv("CTL_PORT");
        if (v != null && !v.trim().isEmpty()) {
            try { return Integer.parseInt(v.trim()); } catch (NumberFormatException ignore) { }
        }
        return DEFAULT_PORT;
    }

    private static String resolveLogPath() {
        String v = System.getProperty("ctl.log");
        if (v == null || v.trim().isEmpty()) v = System.getenv("CTL_LOG");
        if (v != null && !v.trim().isEmpty()) return v.trim();
        String home = System.getProperty("user.home");
        if (home == null || home.trim().isEmpty()) home = ".";
        return home + File.separator + ".eclipse-ctl" + File.separator + "bridge.log";
    }

    private static int resolveUiTimeoutMs() {
        String v = System.getProperty("ctl.uiTimeoutMs");
        if (v != null && !v.trim().isEmpty()) {
            try {
                int n = Integer.parseInt(v.trim());
                if (n > 0) return n;
            } catch (NumberFormatException ignore) { }
        }
        return DEFAULT_UI_TIMEOUT_MS;
    }

    // ------------------------------------------------------------- plumbing

    /** Failure carrying a code from the closed set (mapped onto the wire as {@code ERR <code>}). */
    static final class CtlException extends Exception {
        private static final long serialVersionUID = 1L;
        final String code;
        CtlException(String code, String message) { super(message); this.code = code; }
    }

    /** A single method served on the UI thread. */
    private interface Handler { void run(String arg, List<String> out) throws Exception; }

    /** One row of the self-described method table (design.md §3.2). */
    private static final class Method {
        final String name;
        final String args;
        final String idempotent;
        final String desc;
        final boolean write;
        final boolean onUi;
        final Handler handler;
        Method(String name, String args, boolean write, String idempotent, boolean onUi,
               String desc, Handler handler) {
            this.name = name;
            this.args = args;
            this.write = write;
            this.idempotent = idempotent;
            this.onUi = onUi;
            this.desc = desc;
            this.handler = handler;
        }
    }

    /** Single source of truth for the method surface; {@code sys.help} introspects it. */
    private final Map<String, Method> methods = new LinkedHashMap<String, Method>();

    private final Object logLock = new Object();
    /** Connections being served right now; compared against {@link #MAX_CONNECTIONS}. */
    private final AtomicInteger activeConnections = new AtomicInteger();
    /** Monotonic id used only to name connection threads, so log lines stay unambiguous. */
    private final AtomicLong connectionSeq = new AtomicLong();

    private ServerSocket server;
    private volatile boolean running = true;
    private BundleContext context;

    public LiveBridge() {
        // sys.*
        add("sys.ping", "", false, "true", false,
                "round-trip liveness probe; answers without touching the UI thread",
                (a, o) -> o.add("pong from " + Thread.currentThread().getName()));
        add("sys.env", "", false, "true", false,
                "bridge identity: java/os/protocol/bundle id+version+state/port/timeouts/log path",
                (a, o) -> sysEnv(o));
        add("sys.help", "", false, "true", false,
                "this method table (name|args|write|idempotent|desc)", (a, o) -> sysHelp(a, o));
        add("sys.wait", "[<ms>|jobs-idle]", false, "true", false,
                "wait for org.eclipse.core.runtime.jobs.JobManager to go idle; returns OK with idle=false on timeout",
                (a, o) -> sysWait(a, o));
        // ui.* read
        add("ui.shells", "", false, "true", true,
                "list SWT shells (text/visible/bounds/children)", (a, o) -> shells(o));
        add("ui.tree", "[depth]", false, "true", true,
                "dump the SWT widget tree of the largest visible shell (default depth 3)", (a, o) -> tree(a, o));
        add("ui.parts", "", false, "true", true,
                "perspective + views + editors of the active page (created parts only)", (a, o) -> parts(o));
        add("ui.viewids", "[prefix] [--limit <n>]", false, "true", true,
                "registered view ids (IViewRegistry); no truncation unless --limit is given", (a, o) -> viewIds(a, o));
        add("ui.persp", "", false, "true", true,
                "registered perspectives + the active one", (a, o) -> perspectives(o));
        add("ui.console", "[--tail <n>]", false, "true", true,
                "text of the ACTIVE console (name + last n lines, default 50); ERR notfound when no console exists",
                (a, o) -> uiConsole(a, o));
        // ui.* write
        add("ui.open", "<abs path>", true, "unknown", true,
                "open a file in an editor (CDT C editor, fallback to DefaultTextEditor); idempotent pending P2.1",
                (a, o) -> openEditor(a, o));
        add("ui.close", "<viewId>", true, "true", true,
                "close a view already open in the active page; ERR notfound if it is not open",
                (a, o) -> closeView(a, o));
        // cmd.*
        add("cmd.list", "[prefix] [--limit <n>]", false, "true", true,
                "full command-id export (no silent 300 cap); reports total/matched/returned/truncated",
                (a, o) -> cmdList(a, o));
        add("cmd.query", "<id>", false, "true", true,
                "defined/handled/name/category/parameters of one command", (a, o) -> cmdQuery(a, o));
        add("cmd.run", "<id>", true, "unknown", true,
                "execute a command; ERR disabled/unhandled come from the command framework; idempotent pending P2.1",
                (a, o) -> cmdRun(a, o));
        add("cmd.runp", "<id> <paramId>=<value>", true, "unknown", true,
                "execute a command with one parameter; per-command idempotence, pending P2.1",
                (a, o) -> cmdRunp(a, o));
    }

    private void add(String name, String args, boolean write, String idempotent, boolean onUi,
                     String desc, Handler handler) {
        methods.put(name, new Method(name, args, write, idempotent, onUi, desc, handler));
    }

    // ------------------------------------------------------------ lifecycle

    @Override
    public void start(BundleContext ctx) throws Exception {
        this.context = ctx;
        log("START bundle=" + bsn() + " version=" + bundleVersion()
                + " state=" + ctx.getBundle().getState());
        server = new ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"));
        Thread t = new Thread(new Runnable() {
            @Override public void run() { acceptLoop(); }
        }, "gs32ctl-bridge");
        t.setDaemon(true);
        t.start();
        log("LISTENING on 127.0.0.1:" + PORT + " maxConn=" + MAX_CONNECTIONS
                + " uiTimeoutMs=" + resolveUiTimeoutMs() + " log=" + LOG_PATH);
    }

    @Override
    public void stop(BundleContext ctx) throws Exception {
        running = false;
        try { server.close(); } catch (Exception ignore) { }
        log("STOP");
    }

    /**
     * One thread per connection, at most {@link #MAX_CONNECTIONS} served at a time.
     * A request stuck in a modal dialog now blocks only its own connection.
     */
    private void acceptLoop() {
        while (running) {
            final Socket c;
            try {
                c = server.accept();
            } catch (Exception e) {
                if (running) log("accept failed: " + e);
                continue;
            }
            final int active = activeConnections.incrementAndGet();
            if (active > MAX_CONNECTIONS) {
                activeConnections.decrementAndGet();
                log("BUSY reject (" + (active - 1) + " in flight, max " + MAX_CONNECTIONS + ")");
                rejectBusy(c);
                continue;
            }
            final long seq = connectionSeq.incrementAndGet();
            Thread t = new Thread(new Runnable() {
                @Override public void run() {
                    try { handle(c); }
                    finally { activeConnections.decrementAndGet(); }
                }
            }, "gs32ctl-conn-" + seq);
            t.setDaemon(true);
            t.start();
        }
    }

    private void rejectBusy(Socket c) {
        try {
            c.setSoTimeout((int) SOCKET_READ_TIMEOUT_MS);
            PrintWriter out = new PrintWriter(
                    new OutputStreamWriter(c.getOutputStream(), StandardCharsets.UTF_8), true);
            out.println("ERR " + E_BUSY + " bridge is at capacity ("
                    + MAX_CONNECTIONS + " concurrent connections); retry");
            out.println("END");
            out.flush();
        } catch (Throwable ignore) {
            // the client is gone; nothing to report
        } finally {
            closeQuietly(c);
        }
    }

    // -------------------------------------------------------------- serving

    private void handle(Socket c) {
        long t0 = System.nanoTime();
        String req = "";
        List<String> res = new ArrayList<String>();
        String status = "OK";
        try {
            c.setSoTimeout((int) SOCKET_READ_TIMEOUT_MS);
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
            PrintWriter out = new PrintWriter(
                    new OutputStreamWriter(c.getOutputStream(), StandardCharsets.UTF_8), true);
            try {
                String line = in.readLine();
                req = line == null ? "" : line.trim();
                dispatch(req, res);
            } catch (Throwable t) {
                CtlException e = classify(t);
                status = "ERR " + e.code + " " + oneLine(e.getMessage());
            }
            out.println(oneLine(status));
            for (String s : res) out.println(oneLine(s));
            out.println("END");
            out.flush();
        } catch (Throwable t) {
            // transport-level failure: nothing can be written back
            status = "ERR " + E_INTERNAL + " " + oneLine(String.valueOf(t));
        } finally {
            closeQuietly(c);
        }
        log("REQ \"" + req + "\" -> " + status
                + " (" + ((System.nanoTime() - t0) / 1000000L) + " ms, " + res.size() + " lines)");
    }

    // -------------------------------------------------------------- routing

    private void dispatch(String req, List<String> res) throws Exception {
        int sp = req.indexOf(' ');
        String method = (sp < 0 ? req : req.substring(0, sp)).trim();
        String arg = (sp < 0 ? "" : req.substring(sp + 1).trim());
        Method m = methods.get(method);
        if (m == null) {
            throw new CtlException(E_BADREQUEST,
                    "unknown method: " + (method.isEmpty() ? "<empty request>" : method)
                    + " (see sys.help)");
        }
        if (m.onUi) onUi(m, arg, res);
        else m.handler.run(arg, res);
    }

    /**
     * Hand a task to the SWT event thread and wait at most {@link #resolveUiTimeoutMs()} ms.
     *
     * <p>Deliberately {@code asyncExec}, never {@code syncExec}: {@code syncExec} has no upper
     * bound and would hang this connection behind a modal dialog. The price is that a timeout
     * only ends the <em>wait</em> — the runnable is already queued on the UI thread and may
     * still take effect, so {@code ERR timeout} is not evidence that nothing happened.
     */
    private void onUi(final Method m, final String arg, final List<String> res) throws Exception {
        final Display display = display();
        final int budget = resolveUiTimeoutMs();
        final Object lock = new Object();
        final boolean[] done = { false };
        final Throwable[] err = new Throwable[1];
        // The runnable must NOT write into the caller's list: after a timeout this method
        // returns while the runnable is still queued on the UI thread, and the caller then
        // iterates its own list. Output therefore goes to a private list that is published
        // only once the task has finished (and only while holding the same lock).
        final List<String> local = new ArrayList<String>();
        display.asyncExec(new Runnable() {
            @Override public void run() {
                try {
                    m.handler.run(arg, local);
                } catch (Throwable t) {
                    err[0] = t;
                } finally {
                    synchronized (lock) {
                        done[0] = true;
                        lock.notifyAll();
                    }
                }
            }
        });
        long deadline = System.currentTimeMillis() + budget;
        boolean finished;
        Throwable failure;
        synchronized (lock) {
            while (!done[0]) {
                long remain = deadline - System.currentTimeMillis();
                if (remain <= 0) break;
                try {
                    lock.wait(Math.min(remain, 250L));
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            finished = done[0];
            failure = err[0];
            if (finished) res.addAll(local);
        }
        if (!finished) {
            log("UI-TIMEOUT " + m.name + " arg=\"" + arg + "\" after " + budget
                    + " ms; runnable is still queued on the SWT event thread and may still apply");
            throw new CtlException(E_TIMEOUT, "UI task did not finish within " + budget
                    + " ms; the action is still queued on the SWT event thread and MAY still"
                    + " take effect - read back before retrying");
        }
        if (failure != null) throw classify(failure);
    }

    // ----------------------------------------------------------- sys.* impl

    private void sysEnv(List<String> out) {
        out.add("java.version=" + System.getProperty("java.version"));
        out.add("os.name=" + System.getProperty("os.name"));
        out.add("protocol=" + PROTOCOL_VERSION);
        out.add("bundle=" + bsn() + " version=" + bundleVersion()
                + " id=" + bundleId() + " state=" + bundleState());
        out.add("port=" + PORT + " uiTimeoutMs=" + resolveUiTimeoutMs()
                + " maxConnections=" + MAX_CONNECTIONS + " log=" + LOG_PATH);
        out.add("thread=" + Thread.currentThread().getName());
    }

    private void sysHelp(String arg, List<String> out) throws CtlException {
        if (!arg.isEmpty()) throw new CtlException(E_BADREQUEST, "usage: sys.help");
        out.add("bundle=" + bsn() + " version=" + bundleVersion() + " protocol=" + PROTOCOL_VERSION);
        out.add("fields=name|args|write|idempotent|desc");
        out.add("methods=" + methods.size());
        for (Method m : methods.values()) {
            out.add(m.name + "|" + m.args + "|" + (m.write ? "yes" : "no") + "|"
                    + m.idempotent + "|" + m.desc);
        }
        out.add("codes=" + CODES);
        out.add("note=write=yes methods are asyncExec-dispatched; ERR " + E_TIMEOUT
                + " means the wait ended, not that the action did not run (" + resolveUiTimeoutMs()
                + " ms, -Dctl.uiTimeoutMs)");
        out.add("note=only idempotent=true may be retried automatically; unknown means do not retry (design.md section 7)");
    }

    /**
     * Waits for {@code org.eclipse.core.runtime.jobs.JobManager} to go idle — this is a
     * <em>long-task</em> wait, not a UI event wait. A timeout is a normal result
     * ({@code OK} with {@code idle=false}), not {@code ERR timeout}.
     */
    private void sysWait(String arg, List<String> out) throws CtlException {
        String a = arg.trim();
        String mode;
        long budgetMs;
        if (a.isEmpty()) {
            mode = "snapshot";
            budgetMs = 0L;
        } else if (a.equals("jobs-idle")) {
            mode = "jobs-idle";
            budgetMs = DEFAULT_JOBS_IDLE_WAIT_MS;
        } else {
            mode = "budget";
            budgetMs = parseLong("sys.wait", a);
        }
        IJobManager jm;
        try {
            jm = Job.getJobManager();
        } catch (Throwable t) {
            throw new CtlException(E_NO_WORKBENCH,
                    "job manager is not available: " + oneLine(String.valueOf(t)));
        }
        if (jm == null) throw new CtlException(E_NO_WORKBENCH, "Job.getJobManager() returned null");

        long start = System.currentTimeMillis();
        long deadline = start + budgetMs;
        Job[] jobs = snapshotJobs(jm);
        while (pendingCount(jobs) > 0 && System.currentTimeMillis() < deadline) {
            long remain = deadline - System.currentTimeMillis();
            try {
                Thread.sleep(Math.max(1L, Math.min(200L, remain)));
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                break;
            }
            jobs = snapshotJobs(jm);
        }
        long waited = System.currentTimeMillis() - start;

        int running = 0, waiting = 0, sleeping = 0, none = 0;
        List<String> busy = new ArrayList<String>();
        for (Job j : jobs) {
            int st = stateOf(j);
            if (st == Job.RUNNING) running++;
            else if (st == Job.WAITING) waiting++;
            else if (st == Job.SLEEPING) sleeping++;
            else none++;
            if ((st == Job.RUNNING || st == Job.WAITING) && busy.size() < JOBS_LIST_MAX) {
                busy.add("  busy name=\"" + cut(jobName(j)) + "\" state=" + stateName(st));
            }
        }
        boolean idle = running == 0 && waiting == 0;
        out.add("mode=" + mode);
        out.add("waited_ms=" + waited + " budget_ms=" + budgetMs);
        out.add("idle=" + idle);
        out.add("pending=" + (running + waiting));
        out.add("jobs_total=" + jobs.length + " running=" + running + " waiting=" + waiting
                + " sleeping=" + sleeping + " none=" + none);
        out.addAll(busy);
        out.add("note=JobManager state, not the SWT event queue"
                + " (idle = no RUNNING/WAITING job; sleeping jobs still hold output)");
    }

    // ------------------------------------------------------------ ui.* impl

    private void shells(List<String> out) {
        Display d = Display.getCurrent();
        Shell[] shells = d.getShells();
        out.add("display=" + d + " onThread=" + Thread.currentThread().getName());
        out.add("shellCount=" + shells.length);
        for (Shell s : shells) {
            out.add("shell text=\"" + cut(s.getText()) + "\" vis=" + s.isVisible()
                    + " b=" + s.getBounds() + " children=" + s.getChildren().length
                    + " cls=" + s.getClass().getName());
        }
    }

    private void tree(String arg, List<String> out) throws CtlException {
        int max = 3;
        if (arg.length() > 0) {
            max = parseInt("ui.tree depth", arg);
            if (max < 0) throw new CtlException(E_BADREQUEST, "ui.tree depth must be >= 0");
        }
        Display d = Display.getCurrent();
        Shell[] shells = d.getShells();
        Shell best = null;
        for (Shell s : shells)
            if (s.isVisible() && (best == null || s.getBounds().height > best.getBounds().height)) best = s;
        if (best == null) { out.add("no visible shell"); return; }
        out.add("root text=\"" + cut(best.getText()) + "\" b=" + best.getBounds()
                + " maxDepth=" + max + " thread=" + Thread.currentThread().getName());
        walk(best, 1, max, out, 0);
    }

    private void walk(Widget w, int depth, int max, List<String> out, int budget) {
        if (depth > max || out.size() > 3000) return;
        out.add(pad(depth) + describe(w));
        if (w instanceof org.eclipse.swt.custom.CTabFolder) {
            for (org.eclipse.swt.custom.CTabItem it : ((org.eclipse.swt.custom.CTabFolder) w).getItems())
                out.add(pad(depth + 1) + describe(it));
        }
        if (w instanceof ToolBar) {
            for (ToolItem it : ((ToolBar) w).getItems())
                out.add(pad(depth + 1) + describe(it));
        }
        if (w instanceof Menu) {
            for (MenuItem mi : ((Menu) w).getItems())
                out.add(pad(depth + 1) + describe(mi));
        }
        if (w instanceof Shell) {
            Menu bar = ((Shell) w).getMenuBar();
            if (bar != null) { out.add(pad(depth + 1) + "[menu bar]"); walk(bar, depth + 2, max, out, budget); }
        }
        if (w instanceof Tree)   out.add(pad(depth + 1) + "[TreeItems=" + ((Tree) w).getItems().length + "]");
        if (w instanceof Table)  out.add(pad(depth + 1) + "[TableItems=" + ((Table) w).getItems().length + "]");
        if (w instanceof Composite) {
            for (Control c : ((Composite) w).getChildren()) walk(c, depth + 1, max, out, budget);
        }
    }

    private String describe(Widget w) {
        StringBuilder sb = new StringBuilder(w.getClass().getSimpleName());
        try {
            if (w instanceof Shell) sb.append(" text=\"").append(cut(((Shell) w).getText())).append('"');
            else if (w instanceof Item) sb.append(" text=\"").append(cut(((Item) w).getText())).append('"');
        } catch (Throwable ignore) { }
        if (w instanceof ToolItem) {
            try { sb.append(" tip=\"").append(cut(((ToolItem) w).getToolTipText())).append('"'); }
            catch (Throwable ignore) { }
        }
        if (w instanceof org.eclipse.swt.custom.CTabItem) {
            try { sb.append(" tip=\"").append(cut(((org.eclipse.swt.custom.CTabItem) w).getToolTipText())).append('"'); }
            catch (Throwable ignore) { }
        }
        if (w instanceof Control) {
            Control c = (Control) w;
            try {
                sb.append(" vis=").append(c.isVisible())
                  .append(" en=").append(c.isEnabled())
                  .append(" b=").append(c.getBounds());
            } catch (Throwable ignore) { }
        }
        return sb.toString();
    }

    private void parts(List<String> out) throws CtlException {
        IWorkbench wb = workbench();
        IWorkbenchWindow w = wb.getActiveWorkbenchWindow();
        out.add("workbenchWindows=" + wb.getWorkbenchWindowCount()
                + " activeWindow=" + (w == null ? "null" : w.toString()));
        IWorkbenchPage pg = page();
        IPerspectiveDescriptor pd = pg.getPerspective();
        out.add("perspective id=" + (pd == null ? "null" : pd.getId())
                + " label=\"" + (pd == null ? "" : cut(pd.getLabel())) + "\"");
        IViewReference[] refs = pg.getViewReferences();
        out.add("views=" + refs.length);
        for (IViewReference r : refs) {
            String title = "-";
            try { if (r.getPart(false) != null) title = r.getPart(false).getTitle(); } catch (Throwable ignore) { }
            out.add("  view id=" + r.getId() + " title=\"" + cut(title) + "\"");
        }
        IEditorReference[] eds = pg.getEditorReferences();
        out.add("editors=" + eds.length);
        for (IEditorReference e : eds)
            out.add("  editor id=" + e.getId() + " name=\"" + cut(e.getName()) + "\"");
        out.add("services: EModelService=" + (wb.getService(org.eclipse.e4.ui.workbench.modeling.EModelService.class) != null));
    }

    /**
     * Registered view ids. The previous release silently stopped at 300 entries; the default
     * is now "no cap" and {@code --limit <n>} asks for one explicitly.
     */
    private void viewIds(String arg, List<String> out) throws CtlException {
        String prefix = "";
        Integer limit = null;
        String[] tok = tokens(arg);
        for (int i = 0; i < tok.length; i++) {
            if (tok[i].equals("--limit")) {
                if (i + 1 >= tok.length) throw new CtlException(E_BADREQUEST, "usage: ui.viewids [prefix] [--limit <n>]");
                limit = parseInt("--limit", tok[++i]);
                if (limit < 0) throw new CtlException(E_BADREQUEST, "--limit must be >= 0");
            } else if (prefix.isEmpty()) {
                prefix = tok[i];
            } else {
                throw new CtlException(E_BADREQUEST, "ui.viewids: unexpected argument: " + tok[i]);
            }
        }
        IWorkbench wb = workbench();
        List<String> matched = new ArrayList<String>();
        int total = 0;
        for (IViewDescriptor d : wb.getViewRegistry().getViews()) {
            total++;
            String id = d.getId();
            if (!prefix.isEmpty() && !id.startsWith(prefix)) continue;
            matched.add("  view id=" + id + " label=\"" + cut(d.getLabel()) + "\"");
        }
        int returned = limit == null ? matched.size() : Math.min(limit.intValue(), matched.size());
        for (int i = 0; i < returned; i++) out.add(matched.get(i));
        out.add("registeredViews total=" + total + " matched(prefix=" + prefix + ")=" + matched.size()
                + " returned=" + returned + " truncated=" + (returned < matched.size()));
    }

    private void perspectives(List<String> out) throws CtlException {
        IWorkbench wb = workbench();
        IPerspectiveDescriptor[] ps = wb.getPerspectiveRegistry().getPerspectives();
        out.add("perspectives=" + ps.length);
        for (IPerspectiveDescriptor p : ps)
            out.add("  persp id=" + p.getId() + " label=\"" + cut(p.getLabel()) + "\"");
        IWorkbenchPage pg = page();
        out.add("active=" + (pg.getPerspective() == null ? "null" : pg.getPerspective().getId()));
    }

    /**
     * Text of the <em>active</em> console. Deliberately fails with {@code notfound} when no
     * console exists: an empty success would be indistinguishable from "no console".
     */
    private void uiConsole(String arg, List<String> out) throws CtlException {
        int tail = CONSOLE_TAIL_DEFAULT;
        String[] tok = tokens(arg);
        for (int i = 0; i < tok.length; i++) {
            if (tok[i].equals("--tail")) {
                if (i + 1 >= tok.length) throw new CtlException(E_BADREQUEST, "usage: ui.console [--tail <n>]");
                tail = parseInt("--tail", tok[++i]);
                if (tail < 0) throw new CtlException(E_BADREQUEST, "--tail must be >= 0");
            } else {
                throw new CtlException(E_BADREQUEST, "ui.console: unexpected argument: " + tok[i]);
            }
        }
        IConsoleManager mgr;
        try {
            ConsolePlugin plugin = ConsolePlugin.getDefault();
            if (plugin == null) {
                throw new CtlException(E_NOTFOUND, "console plugin is not active (ConsolePlugin.getDefault() == null)");
            }
            mgr = plugin.getConsoleManager();
        } catch (CtlException e) {
            throw e;
        } catch (Throwable t) {
            throw new CtlException(E_NOTFOUND, "console plugin is not available: " + oneLine(String.valueOf(t)));
        }
        if (mgr == null) throw new CtlException(E_NOTFOUND, "console manager is not available");
        IConsole[] all = mgr.getConsoles();
        if (all == null || all.length == 0) {
            throw new CtlException(E_NOTFOUND, "no console exists (Console view has no console page)");
        }
        IConsole active = activeConsole();
        String source = "active";
        if (active == null) {
            if (all.length == 1) {
                active = all[0];
                source = "single-console";
            } else {
                throw new CtlException(E_NOTFOUND, "no active console (the Console view is not open); "
                        + all.length + " consoles exist, activate one first");
            }
        }
        String name = "-";
        try { name = oneLine(active.getName()); } catch (Throwable ignore) { }
        out.add("console name=\"" + cut(name) + "\" class=" + active.getClass().getName()
                + " source=" + source);
        out.add("consoles total=" + all.length + " othersNotRead=" + (all.length - 1)
                + " (only the active console is read)");
        if (!(active instanceof TextConsole)) {
            out.add("text lines=0 returned=0 truncated=false");
            out.add("textAvailable=false reason=console is not a TextConsole");
            return;
        }
        IDocument doc = ((TextConsole) active).getDocument();
        if (doc == null) {
            out.add("text lines=0 returned=0 truncated=false");
            out.add("textAvailable=false reason=TextConsole returned no document");
            return;
        }
        int lines = doc.getNumberOfLines();
        int from = Math.max(0, lines - tail);
        List<String> tailLines = new ArrayList<String>();
        int chars = 0;
        boolean truncated = from > 0;
        for (int i = from; i < lines; i++) {
            String ln;
            try {
                ln = oneLine(doc.get(doc.getLineOffset(i), doc.getLineLength(i)));
            } catch (Throwable t) {
                truncated = true;
                break;
            }
            if (chars + ln.length() > CONSOLE_MAX_CHARS) {
                truncated = true;
                break;
            }
            tailLines.add(ln);
            chars += ln.length();
        }
        out.add("text lines=" + lines + " returned=" + tailLines.size() + " truncated=" + truncated
                + " tailRequested=" + tail + " charLimit=" + CONSOLE_MAX_CHARS);
        for (String ln : tailLines) out.add("  " + ln);
    }

    private IConsole activeConsole() {
        try {
            IWorkbench wb = PlatformUI.getWorkbench();
            IWorkbenchWindow w = wb == null ? null : wb.getActiveWorkbenchWindow();
            IWorkbenchPage pg = w == null ? null : w.getActivePage();
            if (pg == null) return null;
            IViewPart v = pg.findView(CONSOLE_VIEW_ID);
            if (v == null) {
                IViewReference ref = pg.findViewReference(CONSOLE_VIEW_ID);
                if (ref != null) v = ref.getView(false);
            }
            if (v instanceof IConsoleView) return ((IConsoleView) v).getConsole();
        } catch (Throwable t) {
            log("activeConsole lookup failed: " + t);
        }
        return null;
    }

    // ----------------------------------------------------------- write path

    private void openEditor(String arg, List<String> out) throws Exception {
        if (arg.length() == 0) throw new CtlException(E_BADREQUEST, "usage: ui.open <absolute file path>");
        File f = new File(arg);
        if (!f.isFile()) throw new CtlException(E_NOTFOUND, "not a file: " + f.getAbsolutePath());
        IWorkbenchPage pg = page();
        out.add("file path=" + f.getAbsolutePath());
        IFileStore store = EFS.getLocalFileSystem().fromLocalFile(f);
        IEditorInput input = new FileStoreEditorInput(store);
        IEditorPart part;
        try {
            part = pg.openEditor(input, "org.eclipse.cdt.ui.editor.CEditor");
        } catch (Throwable t) {
            out.add("CDT editor failed: " + oneLine(String.valueOf(t)));
            out.add("fallback -> org.eclipse.ui.DefaultTextEditor");
            part = pg.openEditor(input, "org.eclipse.ui.DefaultTextEditor");
        }
        out.add("opened class=" + (part == null ? "null" : part.getClass().getName()));
        if (part != null) out.add("opened title=\"" + cut(part.getTitle()) + "\"");
        out.add("editors now=" + pg.getEditorReferences().length);
    }

    private void closeView(String arg, List<String> out) throws CtlException {
        if (arg.length() == 0) throw new CtlException(E_BADREQUEST, "usage: ui.close <viewId>");
        IWorkbenchPage pg = page();
        IViewReference ref = pg.findViewReference(arg);
        if (ref == null) throw new CtlException(E_NOTFOUND, "view is not open in the active page: " + arg);
        out.add("before: views=" + pg.getViewReferences().length);
        pg.hideView(ref);
        out.add("hideView done id=" + arg);
        out.add("after: views=" + pg.getViewReferences().length);
    }

    // ------------------------------------------------------------ cmd.* impl

    private ICommandService commandService(IWorkbench wb, List<String> out) {
        ICommandService cs = wb.getService(ICommandService.class);
        out.add("ICommandService via IWorkbench.getService -> " + (cs != null));
        if (cs == null) {
            IEclipseContext ec = wb.getService(IEclipseContext.class);
            out.add("IEclipseContext -> " + (ec != null));
            if (ec != null) cs = ec.get(ICommandService.class);
        }
        return cs;
    }

    /**
     * Full command-id export. The previous release reported {@code total=666} while listing
     * only the first 300 entries; the cap is gone (opt back in with {@code --limit <n>}).
     * Ids that only have a handler and no {@code <command>} declaration are recovered from
     * the {@code org.eclipse.ui.handlers} extension point of active bundles and reported in a
     * separate {@code handlerOnly} block (design.md §6).
     */
    private void cmdList(String arg, List<String> out) throws Exception {
        String prefix = "";
        Integer limit = null;
        String[] tok = tokens(arg);
        for (int i = 0; i < tok.length; i++) {
            if (tok[i].equals("--limit")) {
                if (i + 1 >= tok.length) throw new CtlException(E_BADREQUEST, "usage: cmd.list [prefix] [--limit <n>]");
                limit = parseInt("--limit", tok[++i]);
                if (limit < 0) throw new CtlException(E_BADREQUEST, "--limit must be >= 0");
            } else if (prefix.isEmpty()) {
                prefix = tok[i];
            } else {
                throw new CtlException(E_BADREQUEST, "cmd.list: unexpected argument: " + tok[i]);
            }
        }
        ICommandService cs = commandService(workbench(), out);
        if (cs == null) throw new CtlException(E_INTERNAL, "ICommandService is not available");
        Collection<?> ids = cs.getDefinedCommandIds();
        TreeSet<String> defined = new TreeSet<String>();
        for (Object o : ids) defined.add(String.valueOf(o));
        List<String> matched = new ArrayList<String>();
        for (String id : defined) {
            if (!prefix.isEmpty() && !id.startsWith(prefix)) continue;
            matched.add(id);
        }
        int returned = limit == null ? matched.size() : Math.min(limit.intValue(), matched.size());
        for (int i = 0; i < returned; i++) out.add("  " + matched.get(i));
        out.add("definedCommandIds total=" + defined.size() + " matched(prefix=" + prefix + ")="
                + matched.size() + " returned=" + returned
                + " truncated=" + (returned < matched.size()));

        TreeSet<String> handlerOnly = new TreeSet<String>();
        int inactive = 0;
        String registryState = "unavailable";
        IConfigurationElement[] handlers = null;
        try {
            handlers = Platform.getExtensionRegistry().getConfigurationElementsFor(EP_HANDLERS);
        } catch (Throwable t) {
            log("handler scan failed: " + t);
        }
        if (handlers != null) {
            registryState = "ok";
            for (IConfigurationElement ce : handlers) {
                String cid = ce.getAttribute("commandId");
                if (cid == null || cid.isEmpty()) continue;
                if (defined.contains(cid)) continue;
                if (!prefix.isEmpty() && !cid.startsWith(prefix)) continue;
                if (contributorActive(ce)) handlerOnly.add(cid);
                else inactive++;
            }
        }
        out.add("handlerOnly registry=" + registryState + " total=" + handlerOnly.size()
                + " inactiveContributors=" + inactive
                + " (handler without a <command> declaration; not in getDefinedCommandIds)");
        for (String id : handlerOnly) out.add("  + " + id);
        out.add("caveat=handler-only ids cannot be enumerated through ICommandService;"
                + " this section is a best-effort scan of plugin.xml contributions of active bundles"
                + (inactive > 0 ? " (" + inactive + " more skipped from inactive bundles)" : ""));
    }

    private static boolean contributorActive(IConfigurationElement ce) {
        try {
            Bundle b = Platform.getBundle(ce.getContributor().getName());
            if (b == null) return false;
            int st = b.getState();
            return (st & (Bundle.STARTING | Bundle.ACTIVE)) != 0;
        } catch (Throwable t) {
            return false;
        }
    }

    private void cmdQuery(String id, List<String> out) throws CtlException {
        if (id.length() == 0) throw new CtlException(E_BADREQUEST, "usage: cmd.query <id>");
        ICommandService cs = commandService(workbench(), out);
        if (cs == null) throw new CtlException(E_INTERNAL, "ICommandService is not available");
        Command c = cs.getCommand(id);
        if (c == null) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        boolean cmdDefined = c.isDefined();
        boolean handled = c.isHandled();
        if (!cmdDefined && !handled) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        out.add("id=" + c.getId());
        out.add("defined=" + cmdDefined);
        out.add("handled=" + handled);
        if (cmdDefined) {
            try { out.add("name=\"" + cut(c.getName()) + "\""); }
            catch (Throwable t) { out.add("name=<" + oneLine(String.valueOf(t)) + ">"); }
            try { out.add("category=" + (c.getCategory() == null ? "null" : c.getCategory().getId())); }
            catch (Throwable t) { out.add("category=<" + oneLine(String.valueOf(t)) + ">"); }
            try {
                IParameter[] ps = c.getParameters();
                if (ps == null) {
                    out.add("parameters=null (command declares none)");
                } else {
                    out.add("parameters=" + ps.length);
                    for (IParameter pp : ps)
                        out.add("  param id=" + pp.getId() + " name=\"" + cut(pp.getName()) + "\"");
                }
            } catch (Throwable t) { out.add("parameters=<" + oneLine(String.valueOf(t)) + ">"); }
        }
    }

    private void cmdRun(String id, List<String> out) throws Exception {
        if (id.length() == 0) throw new CtlException(E_BADREQUEST, "usage: cmd.run <id>");
        IWorkbench wb = workbench();
        ICommandService cs = commandService(wb, out);
        if (cs == null) throw new CtlException(E_INTERNAL, "ICommandService is not available");
        IHandlerService hs = wb.getService(IHandlerService.class);
        out.add("IHandlerService -> " + (hs != null));
        if (hs == null) throw new CtlException(E_INTERNAL, "IHandlerService is not available");
        Command c = cs.getCommand(id);
        if (c == null) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        out.add("before: defined=" + c.isDefined() + " handled=" + c.isHandled());
        if (!c.isDefined() && !c.isHandled()) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        Object r = hs.executeCommand(id, null);
        out.add("executeCommand returned: " + describeResult(r));
        out.add("OK executed " + id);
    }

    private void cmdRunp(String arg, List<String> out) throws Exception {
        int sp = arg.indexOf(' ');
        if (sp < 0) throw new CtlException(E_BADREQUEST, "usage: cmd.runp <commandId> <paramId>=<value>");
        String id = arg.substring(0, sp).trim();
        String kv = arg.substring(sp + 1).trim();
        int eq = kv.indexOf('=');
        if (id.length() == 0 || eq < 0) {
            throw new CtlException(E_BADREQUEST, "usage: cmd.runp <commandId> <paramId>=<value>");
        }
        String pname = kv.substring(0, eq).trim();
        String pvalue = kv.substring(eq + 1);
        if (pname.isEmpty()) throw new CtlException(E_BADREQUEST, "parameter id is empty");

        IWorkbench wb = workbench();
        ICommandService cs = commandService(wb, out);
        if (cs == null) throw new CtlException(E_INTERNAL, "ICommandService is not available");
        IHandlerService hs = wb.getService(IHandlerService.class);
        out.add("IHandlerService -> " + (hs != null));
        if (hs == null) throw new CtlException(E_INTERNAL, "IHandlerService is not available");
        Command c = cs.getCommand(id);
        if (c == null) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        if (!c.isDefined() && !c.isHandled()) throw new CtlException(E_NOTFOUND, "no such command id: " + id);
        IParameter p = c.getParameter(pname);
        if (p == null) throw new CtlException(E_NOTFOUND, "command " + id + " has no parameter " + pname);
        ParameterizedCommand pc = new ParameterizedCommand(c,
                new Parameterization[] { new Parameterization(p, pvalue) });
        out.add("parameter " + pname + "=" + pvalue);
        out.add("parameterizedCommand id=" + pc.getId());
        Object r = hs.executeCommand(pc, null);
        out.add("executeCommand returned: " + describeResult(r));
        out.add("OK executed " + pc.getId());
    }

    // ------------------------------------------------------------- helpers

    private Display display() throws CtlException {
        IWorkbench wb;
        try {
            wb = PlatformUI.getWorkbench();
        } catch (Throwable t) {
            throw new CtlException(E_NO_WORKBENCH,
                    "workbench is not created yet: " + oneLine(String.valueOf(t)));
        }
        if (wb == null) throw new CtlException(E_NO_WORKBENCH, "PlatformUI.getWorkbench() returned null");
        Display d = wb.getDisplay();
        if (d == null) throw new CtlException(E_NO_WORKBENCH, "workbench has no display");
        return d;
    }

    private IWorkbench workbench() throws CtlException {
        display();
        IWorkbench wb = PlatformUI.getWorkbench();
        if (wb == null) throw new CtlException(E_NO_WORKBENCH, "PlatformUI.getWorkbench() returned null");
        return wb;
    }

    private IWorkbenchPage page() throws CtlException {
        IWorkbench wb = workbench();
        IWorkbenchWindow w = wb.getActiveWorkbenchWindow();
        if (w == null) throw new CtlException(E_NO_WORKBENCH, "no active workbench window");
        IWorkbenchPage pg = w.getActivePage();
        if (pg == null) throw new CtlException(E_NO_WORKBENCH, "no active workbench page");
        return pg;
    }

    /** Maps every failure onto exactly one code of the closed set. */
    private static CtlException classify(Throwable t) {
        if (t instanceof CtlException) return (CtlException) t;
        if (t instanceof NotEnabledException) {
            return new CtlException(E_DISABLED, "command is disabled: " + oneLine(String.valueOf(t)));
        }
        if (t instanceof NotHandledException) {
            return new CtlException(E_UNHANDLED, "command has no handler for this context: "
                    + oneLine(String.valueOf(t)));
        }
        String msg = oneLine(String.valueOf(t));
        if (t instanceof IllegalStateException && msg.indexOf("Workbench has not been created") >= 0) {
            return new CtlException(E_NO_WORKBENCH, msg);
        }
        return new CtlException(E_INTERNAL, t.getClass().getSimpleName()
                + (t.getMessage() == null ? "" : ": " + oneLine(t.getMessage())));
    }

    private static String describeResult(Object r) {
        if (r == null) return "null";
        return oneLine(r.getClass().getName() + " " + String.valueOf(r));
    }

    private static String oneLine(String s) {
        if (s == null) return "";
        StringBuilder b = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            b.append(ch == '\n' || ch == '\r' || ch == '\t' ? ' ' : ch);
        }
        return b.toString();
    }

    private static String[] tokens(String arg) {
        String a = arg == null ? "" : arg.trim();
        if (a.isEmpty()) return new String[0];
        return a.split("\\s+");
    }

    private static int parseInt(String what, String s) throws CtlException {
        try {
            return Integer.parseInt(s.trim());
        } catch (NumberFormatException e) {
            throw new CtlException(E_BADREQUEST, what + " must be an integer, got: " + s);
        }
    }

    private static long parseLong(String what, String s) throws CtlException {
        long v;
        try {
            v = Long.parseLong(s.trim());
        } catch (NumberFormatException e) {
            throw new CtlException(E_BADREQUEST,
                    "usage: sys.wait [<ms>|jobs-idle]; got: " + s);
        }
        if (v < 0) throw new CtlException(E_BADREQUEST, what + " must be >= 0");
        return v;
    }

    private static Job[] snapshotJobs(IJobManager jm) {
        try {
            Job[] jobs = jm.find(null);
            return jobs == null ? new Job[0] : jobs;
        } catch (Throwable t) {
            return new Job[0];
        }
    }

    private static int pendingCount(Job[] jobs) {
        int n = 0;
        for (Job j : jobs) {
            int st = stateOf(j);
            if (st == Job.RUNNING || st == Job.WAITING) n++;
        }
        return n;
    }

    private static int stateOf(Job j) {
        try { return j.getState(); } catch (Throwable t) { return Job.NONE; }
    }

    private static String jobName(Job j) {
        try { return j.getName(); } catch (Throwable t) { return "?"; }
    }

    private static String stateName(int st) {
        if (st == Job.RUNNING) return "RUNNING";
        if (st == Job.WAITING) return "WAITING";
        if (st == Job.SLEEPING) return "SLEEPING";
        return "NONE";
    }

    private static String pad(int d) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < d; i++) b.append("  ");
        return b.toString();
    }

    private static String cut(String s) {
        if (s == null) return "";
        s = oneLine(s);
        return s.length() > 90 ? s.substring(0, 90) + "..." : s;
    }

    private static void closeQuietly(Socket c) {
        try { c.close(); } catch (Throwable ignore) { }
    }

    private String bsn() {
        try {
            Bundle b = context == null ? null : context.getBundle();
            if (b != null && b.getSymbolicName() != null) return b.getSymbolicName();
        } catch (Throwable ignore) { }
        return "eclipse-ctl.bridge";
    }

    private String bundleVersion() {
        try {
            Bundle b = context == null ? null : context.getBundle();
            if (b != null) return String.valueOf(b.getVersion());
        } catch (Throwable ignore) { }
        return "unknown";
    }

    private String bundleId() {
        try {
            Bundle b = context == null ? null : context.getBundle();
            if (b != null) return String.valueOf(b.getBundleId());
        } catch (Throwable ignore) { }
        return "unknown";
    }

    private String bundleState() {
        try {
            Bundle b = context == null ? null : context.getBundle();
            if (b != null) return String.valueOf(b.getState());
        } catch (Throwable ignore) { }
        return "unknown";
    }

    /** Every request, its outcome and its duration land here (design-project.md §17.2). */
    private void log(String msg) {
        String line = "[" + new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS").format(new Date())
                + "] [" + Thread.currentThread().getName() + "] " + oneLine(msg) + "\n";
        synchronized (logLock) {
            try {
                Path p = Paths.get(LOG_PATH);
                Path parent = p.getParent();
                if (parent != null) Files.createDirectories(parent);
                Files.write(p, line.getBytes(StandardCharsets.UTF_8),
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (Throwable ignore) {
                // never let logging break the bridge
            }
        }
    }
}
