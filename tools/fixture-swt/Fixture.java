/*
 * ctl-fixture v2 —— 最小 SWT 夹具（eclipse-ctl P6.1 / P6.4）
 *
 * v1 只回答了 Button 与 Text。v2 加进 **MenuItem / ToolItem / Tree** 三类，
 * 目的是回答 P6.4 的那个问题：**这些控件有没有自己的 HWND？**
 *   —— 有 HWND 才可能"元素寻址 + 消息注入"；没有就只能靠坐标/键盘/或桥内调用。
 *
 * 唯一可观测 = 窗口标题（可用 win-enum.ps1 直接读，不需要像素）：
 *   基线                      ctl-fixture
 *   点 &Go 第 n 次            ctl-fixture GO <n>
 *   文本框被改成 X            ctl-fixture TEXT <X>
 *   收到按键 keyCode k        ctl-fixture KEY <k>
 *   菜单项 &MenuAct 选中      ctl-fixture MENU <n>
 *   工具项 &ToolAct 按下      ctl-fixture TOOL <n>
 *   树项选中                  ctl-fixture TREE <n>
 */
import org.eclipse.swt.SWT;
import org.eclipse.swt.events.KeyAdapter;
import org.eclipse.swt.events.KeyEvent;
import org.eclipse.swt.events.ModifyEvent;
import org.eclipse.swt.events.ModifyListener;
import org.eclipse.swt.events.SelectionAdapter;
import org.eclipse.swt.events.SelectionEvent;
import org.eclipse.swt.layout.FillLayout;
import org.eclipse.swt.layout.RowLayout;
import org.eclipse.swt.widgets.Button;
import org.eclipse.swt.widgets.Display;
import org.eclipse.swt.widgets.Menu;
import org.eclipse.swt.widgets.MenuItem;
import org.eclipse.swt.widgets.Shell;
import org.eclipse.swt.widgets.Text;
import org.eclipse.swt.widgets.ToolBar;
import org.eclipse.swt.widgets.ToolItem;
import org.eclipse.swt.widgets.Tree;
import org.eclipse.swt.widgets.TreeItem;

public class Fixture {

    static final String BASE = "ctl-fixture";
    static int goCount = 0;
    static int menuCount = 0;
    static int toolCount = 0;
    static Shell shell;

    public static void main(String[] args) {
        Display display = new Display();
        shell = new Shell(display);
        shell.setText(BASE);
        shell.setLayout(new FillLayout(SWT.VERTICAL));

        // ---- 菜单栏（MenuItem 在 Win32 上是 HMENU 条目，不是窗口）----
        Menu bar = new Menu(shell, SWT.BAR);
        MenuItem top = new MenuItem(bar, SWT.CASCADE);
        top.setText("&File");
        Menu drop = new Menu(shell, SWT.DROP_DOWN);
        top.setMenu(drop);
        MenuItem menuAct = new MenuItem(drop, SWT.PUSH);
        menuAct.setText("&MenuAct");
        menuAct.addSelectionListener(new SelectionAdapter() {
            @Override public void widgetSelected(SelectionEvent e) {
                menuCount++;
                shell.setText(BASE + " MENU " + menuCount);
            }
        });
        shell.setMenuBar(bar);

        // ---- 工具栏（ToolItem 由 ToolBar 自绘）----
        ToolBar tb = new ToolBar(shell, SWT.FLAT | SWT.WRAP);
        ToolItem toolAct = new ToolItem(tb, SWT.PUSH);
        toolAct.setText("&ToolAct");
        toolAct.addSelectionListener(new SelectionAdapter() {
            @Override public void widgetSelected(SelectionEvent e) {
                toolCount++;
                shell.setText(BASE + " TOOL " + toolCount);
            }
        });

        Button go = new Button(shell, SWT.PUSH);
        go.setText("&Go");
        go.addSelectionListener(new SelectionAdapter() {
            @Override public void widgetSelected(SelectionEvent e) {
                goCount++;
                shell.setText(BASE + " GO " + goCount);
            }
        });

        Text field = new Text(shell, SWT.BORDER);
        field.setText("");
        field.addModifyListener(new ModifyListener() {
            @Override public void modifyText(ModifyEvent e) {
                shell.setText(BASE + " TEXT " + field.getText());
            }
        });
        field.addKeyListener(new KeyAdapter() {
            @Override public void keyPressed(KeyEvent e) {
                shell.setText(BASE + " KEY " + e.keyCode);
            }
        });

        // ---- 树（Tree 在 Win32 上是 SysTreeView32，有自己的 HWND）----
        final Tree tree = new Tree(shell, SWT.BORDER | SWT.SINGLE);
        TreeItem ti = new TreeItem(tree, SWT.NONE);
        ti.setText("ctl-item-1");
        tree.addSelectionListener(new SelectionAdapter() {
            @Override public void widgetSelected(SelectionEvent e) {
                shell.setText(BASE + " TREE " + tree.getSelectionCount());
            }
        });

        shell.setSize(420, 420);
        shell.open();
        System.out.println("[fixture] up title=" + shell.getText());

        while (!shell.isDisposed()) {
            if (!display.readAndDispatch()) display.sleep();
        }
        display.dispose();
    }
}
