import { useEffect, useState, ReactNode } from "react";
import { ButtonItem, PanelSection, PanelSectionRow, TextField, staticClasses, Navigation, Focusable, SidebarNavigation, Field, DialogButton, ToggleField } from "@decky/ui";
import { callable, definePlugin, toaster, routerHook } from "@decky/api";
import { FaCat, FaCloudDownloadAlt, FaSlidersH, FaInfoCircle } from "react-icons/fa";

type Status = {
  version: string; logged_in: boolean; message: string; core: string;
  auth_state: string; auth_message: string;
  subscription_state: string; subscription_message: string;
};
type DashboardData = {
  subscription: string; source: string; cache_updated?: number; error: string;
  nodes: { name: string; status: string; delay_ms: number | null }[];
  selected_node: string; running: boolean;
  service_available: boolean; dashboard_url: string;
};
const getStatus = callable<[], Status>("get_status");
const login = callable<[account: string, password: string], Status>("login");
const checkCore = callable<[], Status>("check_core");
const refreshSubscription = callable<[], Status>("refresh_subscription");
const exportDiagnostic = callable<[], string>("export_diagnostic");
const getDashboard = callable<[refresh: boolean], DashboardData>("get_dashboard");
const setAcceleration = callable<[enabled: boolean], DashboardData>("set_acceleration");
const settingsPath = "/miaozi-deck/settings";

function openDashboard(data?: DashboardData) {
  if (data?.dashboard_url) {
    Navigation.NavigateToExternalWeb(data.dashboard_url);
    Navigation.CloseSideMenus();
  }
}

function Home() {
  const [data, setData] = useState<DashboardData>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const refresh = () => getDashboard(false).then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError("暂时无法读取订阅信息。"); });
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  async function toggle() {
    setBusy(true); setError("");
    try { setData(await setAcceleration(!data?.running)); }
    catch { setError("操作未完成，请稍后重试。"); }
    finally { setBusy(false); }
  }
  return <PanelSection title="喵子">
    <PanelSectionRow><div style={{ fontSize: 13, lineHeight: 1.7, paddingBottom: 12 }}>
      <div>订阅：{data ? data.nodes.length ? data.subscription : "尚未接入" : "正在读取…"}</div>
      <div>线路：{data ? `${data.nodes.length} 个 · ${data.source === "online" ? "在线订阅" : "本机订阅"}` : "—"}</div>
      <div>当前节点：{data?.selected_node || "—"}</div>
      <div style={{ color: data?.running ? "#8be3b0" : "#f3ce86" }}>{data?.running ? "加速已开启 · 游戏与桌面模式生效" : "加速已关闭"}</div>
      {(error || data?.error) && <div>{error || data?.error}</div>}
    </div></PanelSectionRow>
    <PanelSectionRow><ToggleField label="网络加速" checked={!!data?.running} disabled={busy || !data?.service_available} onChange={() => void toggle()} /></PanelSectionRow>
    <PanelSectionRow><ButtonItem layout="below" disabled={!data?.dashboard_url} onClick={() => openDashboard(data)}>打开 Yacd 仪表盘</ButtonItem></PanelSectionRow>
    <PanelSectionRow><ButtonItem layout="below" onClick={() => {
      Navigation.Navigate(`${settingsPath}/subscription`); Navigation.CloseSideMenus();
    }}>设置</ButtonItem></PanelSectionRow>
  </PanelSection>;
}

// SidebarNavigation owns page height, controller navigation and scrolling.
// Keep each page short; do not nest another full-height scroll container.
function SettingsBody({ children }: { children: ReactNode }) {
  return <div style={{ padding: "0 12px 32px", minWidth: 0 }}>{children}</div>;
}

function ActionRow({ label, description, children, disabled, onClick }: {
  label: string; description?: string; children: ReactNode;
  disabled?: boolean; onClick: () => void;
}) {
  return <Field label={label} description={description} padding="compact"
    childrenLayout="inline" childrenContainerWidth="min" inlineWrap="keep-inline">
    <DialogButton disabled={disabled} onClick={onClick}
      style={{ width: 144, minWidth: 144, maxWidth: 144, padding: "10px 12px", boxSizing: "border-box" }}>
      {children}
    </DialogButton>
  </Field>;
}

function Notice({ children }: { children: ReactNode }) {
  return children ? <div role="status" aria-live="polite"
    style={{ fontSize: 13, lineHeight: 1.5, padding: "12px 0", overflowWrap: "anywhere" }}>{children}</div> : null;
}

function Settings() {
  const [data, setData] = useState<DashboardData>();
  const [status, setStatus] = useState<Status>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [showLogin, setShowLogin] = useState(false);
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const hasSubscription = !!data?.nodes.length;

  useEffect(() => {
    let active = true;
    Promise.all([getDashboard(false), getStatus()]).then(([dashboard, accountStatus]) => {
      if (active) { setData(dashboard); setStatus(accountStatus); }
    }).catch(() => { if (active) setMessage("暂时无法读取状态，请返回后重试。"); });
    return () => { active = false; };
  }, []);

  async function sync() {
    setBusy(true); setMessage("正在同步订阅，请稍候…");
    try {
      const result = await refreshSubscription();
      setStatus(result); setMessage(result.subscription_message);
      setData(await getDashboard(false));
    } catch { setMessage("同步未完成，请稍后重试。已有订阅可继续使用。"); }
    finally { setBusy(false); }
  }

  async function submit() {
    const enteredPassword = password;
    setPassword(""); setBusy(true); setMessage("正在连接账号…");
    try {
      const result = await login(account, enteredPassword);
      setStatus(result);
      if (!result.logged_in) { setMessage(result.auth_message); return; }
      setShowLogin(false); setAccount(""); setMessage("账号已连接，正在同步订阅…");
      const updated = await refreshSubscription();
      setStatus(updated); setMessage(updated.subscription_message);
      setData(await getDashboard(false));
    } catch { setMessage("账号操作未完成，请稍后重试。"); }
    finally { setBusy(false); }
  }

  async function toggle(enabled: boolean) {
    setBusy(true); setMessage("");
    try { const result = await setAcceleration(enabled); setData(result); setMessage(result.error); }
    catch { setMessage("加速操作未完成，请稍后重试。"); }
    finally { setBusy(false); }
  }

  async function diagnose() {
    setBusy(true); setMessage("");
    try { const result = await checkCore(); setStatus(result); setMessage(result.message); }
    catch { setMessage("检查未完成，请稍后重试。"); }
    finally { setBusy(false); }
  }

  async function exportReport() {
    setBusy(true);
    try {
      await exportDiagnostic();
      setMessage("诊断已保存到 Downloads 文件夹。");
      toaster.toast({ title: "诊断已导出", body: "文件位于 Downloads，不含账号密码和令牌。" });
    } catch { setMessage("导出失败，请稍后重试。"); }
    finally { setBusy(false); }
  }

  const subscription = <SettingsBody>
    {showLogin ? <>
      <div style={{ fontSize: 14, lineHeight: 1.5, paddingBottom: 12 }}>连接账号后自动同步订阅。账号密码不保存。</div>
      <TextField label="喵子账号 / 邮箱" value={account} disabled={busy} onChange={event => setAccount(event.target.value)} bShowClearAction />
      <TextField label="密码" value={password} disabled={busy} bIsPassword onChange={event => setPassword(event.target.value)} />
      <Focusable flow-children="row" style={{ display: "flex", gap: 12, paddingTop: 16 }}>
        <DialogButton style={{ width: 144, minWidth: 0 }} disabled={busy || !account.trim() || !password} onClick={() => void submit()}>登录并同步</DialogButton>
        <DialogButton style={{ width: 100, minWidth: 0 }} disabled={busy} onClick={() => { setShowLogin(false); setPassword(""); setMessage(""); }}>取消</DialogButton>
      </Focusable>
    </> : <>
      <Field label="当前订阅" description={hasSubscription ? `${data?.subscription} · ${data?.nodes.length} 个节点` : "接入账号后获取节点。"} padding="compact">
        <span style={{ color: hasSubscription ? "#8be3b0" : "#c0c8d2", whiteSpace: "nowrap" }}>{data ? hasSubscription ? "已就绪" : "未接入" : "读取中…"}</span>
      </Field>
      <ActionRow label="更新订阅" description={data?.cache_updated ? `上次更新：${new Date(data.cache_updated * 1000).toLocaleString()}` : "获取最新节点，更新失败保留现有订阅。"}
        disabled={busy || !data} onClick={() => void sync()}>{busy ? "处理中…" : "同步订阅"}</ActionRow>
      <ActionRow label="喵子账号" description={hasSubscription ? "已有订阅可直接使用，无需重复登录。" : status?.logged_in ? "账号已连接，可以同步订阅。" : "使用喵子账号获取订阅。"}
        disabled={busy || !status} onClick={() => { setShowLogin(true); setMessage(""); }}>{hasSubscription || status?.logged_in ? "更换账号" : "连接账号"}</ActionRow>
      <div style={{ fontSize: 12, opacity: 0.65, paddingTop: 10 }}>当前为手动更新。节点切换和测速请打开 Yacd 仪表盘。</div>
    </>}
    <Notice>{message || data?.error}</Notice>
  </SettingsBody>;

  const acceleration = <SettingsBody>
    <ToggleField label="网络加速" description="切换游戏与桌面模式后继续生效。" checked={!!data?.running}
      disabled={busy || !data?.service_available} onChange={enabled => void toggle(enabled)} />
    <Field label="当前节点" padding="compact" childrenContainerWidth="min">
      <span style={{ maxWidth: 250, overflowWrap: "anywhere", fontSize: 14 }}>{data?.selected_node || "尚未选择"}</span>
    </Field>
    <ActionRow label="Yacd 仪表盘" description="切换节点、查看延迟、批量测速。" disabled={!data?.dashboard_url}
      onClick={() => openDashboard(data)}>打开仪表盘</ActionRow>
    <div style={{ fontSize: 12, opacity: 0.65, paddingTop: 12 }}>当前节点代理公网流量，局域网直连。开关和节点选择会自动保存。</div>
    <Notice>{message || data?.error}</Notice>
  </SettingsBody>;

  const diagnostics = <SettingsBody>
    <ActionRow label="导出诊断" description="遇到问题时使用，不包含账号密码或订阅地址。" disabled={busy} onClick={() => void exportReport()}>导出文件</ActionRow>
    <ActionRow label="检查内核" description="仅检查组件通讯，不改变加速开关。" disabled={busy} onClick={() => void diagnose()}>运行检查</ActionRow>
    <Field label="插件版本" padding="compact">{status?.version || "0.1.0-alpha.9"}</Field>
    <div style={{ fontSize: 12, opacity: 0.65, paddingTop: 12 }}>非官方私人使用版本。请保留 Deck 上的喵子原版客户端文件。</div>
    <Notice>{message}</Notice>
  </SettingsBody>;

  return <SidebarNavigation title="喵子设置" showTitle pages={[
    { title: "订阅与账号", icon: <FaCloudDownloadAlt />, route: `${settingsPath}/subscription`, content: subscription },
    { title: "加速设置", icon: <FaSlidersH />, route: `${settingsPath}/acceleration`, content: acceleration },
    { title: "帮助与诊断", icon: <FaInfoCircle />, route: `${settingsPath}/diagnostics`, content: diagnostics },
  ]} />;
}

export default definePlugin(() => {
  routerHook.addRoute(settingsPath, Settings);
  return {
    name: "Miaozi Deck",
    titleView: <div className={staticClasses.Title}>喵子 Deck</div>,
    content: <Home />,
    icon: <FaCat />,
    onDismount() { routerHook.removeRoute(settingsPath); },
  };
});
