"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ChevronDown, Eye, EyeOff, Globe, Loader2 } from "lucide-react";

import { requestGuideOnNextEntry } from "@/components/onboarding/guide-storage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useLlmConfig } from "@/contexts/LlmConfigContext";
import {
  PROVIDER_PRESETS,
  WEB_SEARCH_NOTICE,
  fetchLlmConfig,
  saveLlmConfig,
  testLlmConfig,
} from "@/lib/llm-config";
import type { LlmProbeResponse } from "@/types/config";

interface SetupClientProps {
  /** 设置页复用本组件：标题措辞不同，且保存后不跳首页。 */
  mode?: "setup" | "settings";
}

type FieldErrors = { base_url?: string; api_key?: string; model?: string };

export function SetupClient({ mode = "setup" }: SetupClientProps) {
  const router = useRouter();
  const { refresh: refreshLlmConfig } = useLlmConfig();
  const isSetup = mode === "setup";

  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [auxModel, setAuxModel] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [modelHint, setModelHint] = useState("填模型名称或 ID");

  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [probe, setProbe] = useState<LlmProbeResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [keyPlaceholder, setKeyPlaceholder] = useState("");

  // 设置页：把已存的配置回填，方便只改模型不重填 Key。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const cfg = await fetchLlmConfig();
        if (cancelled || !cfg.configured) return;
        setBaseUrl(cfg.base_url);
        setModel(cfg.model);
        setAuxModel(cfg.aux_model);
        if (cfg.aux_model) setShowAdvanced(true);
        // 后端不会回传明文 Key，这里用脱敏值当占位符提示「已填过」。
        setKeyPlaceholder(cfg.api_key_masked ? `${cfg.api_key_masked}（如需更换请重新输入）` : "");
      } catch {
        // 拿不到就当全新配置，不打扰用户
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const validate = useCallback((): boolean => {
    const next: FieldErrors = {};
    if (!baseUrl.trim()) next.base_url = "请填写 Base URL";
    else if (!/^https?:\/\//i.test(baseUrl.trim())) next.base_url = "Base URL 需以 http:// 或 https:// 开头";
    if (!apiKey.trim()) next.api_key = "请填写 API Key";
    if (!model.trim()) next.model = "请填写模型名称";
    setErrors(next);
    return Object.keys(next).length === 0;
  }, [baseUrl, apiKey, model]);

  const payload = useCallback(
    () => ({
      base_url: baseUrl.trim(),
      api_key: apiKey.trim(),
      model: model.trim(),
      aux_model: auxModel.trim(),
    }),
    [baseUrl, apiKey, model, auxModel],
  );

  const handleTest = useCallback(async () => {
    setSaveError(null);
    setSaved(false);
    if (!validate()) return;
    setTesting(true);
    setProbe(null);
    try {
      const result = await testLlmConfig(payload());
      setProbe(result);
      // 后端可能把缺 /v1 的地址补全后才测通，回填让用户看到真正生效的地址。
      if (result.ok && result.base_url && result.base_url !== baseUrl.trim()) {
        setBaseUrl(result.base_url);
      }
    } catch (e) {
      setProbe({
        ok: false,
        message: e instanceof Error ? e.message : "测试失败",
        web_search_supported: false,
        web_search_message: "",
        base_url: "",
      });
    } finally {
      setTesting(false);
    }
  }, [validate, payload, baseUrl]);

  const handleSave = useCallback(async () => {
    setSaveError(null);
    setSaved(false);
    if (!validate()) return;
    setSaving(true);
    try {
      // 后端保存前会自己再测一遍，测不通直接 400，不会存下一份用不了的配置。
      const savedStatus = await saveLlmConfig(payload());
      if (isSetup) {
        // 配置完成 = 玩家第一次真正进游戏，请引导在落地后弹出来。
        requestGuideOnNextEntry();
        // 必须在跳转前把全局的 LlmConfigContext 同步成「已配置」。
        // 否则 SetupGuard 读到的 status 还是挂载时缓存的 unconfigured，
        // 会在跳到 "/" 的同一时刻把用户弹回 /setup，表现为「保存成功但卡在配置页」。
        await refreshLlmConfig();
        router.replace("/");
      } else {
        setSaved(true);
        setApiKey("");
        // 存下来的可能是自动补全 /v1 之后的地址，回填成实际生效的那个。
        setBaseUrl(savedStatus.base_url);
        setKeyPlaceholder(
          savedStatus.api_key_masked ? `${savedStatus.api_key_masked}（如需更换请重新输入）` : "",
        );
        setProbe(null);
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [validate, payload, isSetup, router, refreshLlmConfig]);

  const busy = testing || saving;

  // 表单主体，setup 与 settings 两种模式共用；两种模式的外层容器不同（见下方 return）。
  const content = (
    <div className="w-full max-w-lg space-y-6 py-8">
      <div className="flex flex-col items-center text-center">
        <Image
          src="/logo-with-text.png"
          alt="心动实验室"
          width={144}
          height={144}
          priority
          className="size-36"
        />
        <h1 className="mt-3 text-base font-medium text-muted-foreground">
          {isSetup ? "开始之前，先配置你的大模型" : "大模型设置"}
        </h1>
        {isSetup && (
          <p className="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
            这个游戏需要大模型来驱动角色对话。填入你自己的 API 信息即可开始，
            配置只保存在你自己的电脑上。
          </p>
        )}
      </div>

      <section className="border-primary/20 bg-card/90 rounded-3xl border p-5 shadow-sm backdrop-blur-sm">
        <div className="space-y-4">
          <div>
            <label className="mb-2 block text-sm font-medium">常用供应商</label>
            <div className="flex flex-wrap gap-2">
              {PROVIDER_PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    setBaseUrl(p.baseUrl);
                    setModelHint(p.modelHint);
                    setErrors((prev) => ({ ...prev, base_url: undefined }));
                    setProbe(null);
                  }}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                    baseUrl === p.baseUrl
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground mt-2 text-xs">
              点一下自动填地址，也可以手填任何 OpenAI 兼容服务。
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="base-url">
              Base URL
            </label>
            <Input
              id="base-url"
              type="text"
              placeholder="https://api.openai.com/v1"
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setErrors((prev) => ({ ...prev, base_url: undefined }));
                setProbe(null);
              }}
              aria-invalid={!!errors.base_url}
            />
            {errors.base_url && (
              <p className="text-destructive mt-1 text-xs" role="alert">
                {errors.base_url}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="api-key">
              API Key
            </label>
            <div className="relative">
              <Input
                id="api-key"
                type={showKey ? "text" : "password"}
                placeholder={keyPlaceholder || "sk-..."}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setErrors((prev) => ({ ...prev, api_key: undefined }));
                  setProbe(null);
                }}
                className="pr-10"
                autoComplete="off"
                aria-invalid={!!errors.api_key}
              />
              <button
                type="button"
                tabIndex={-1}
                aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}
                className="text-muted-foreground hover:text-foreground absolute top-1/2 right-3 -translate-y-1/2"
                onClick={() => setShowKey((v) => !v)}
              >
                {showKey ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
              </button>
            </div>
            {errors.api_key && (
              <p className="text-destructive mt-1 text-xs" role="alert">
                {errors.api_key}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium" htmlFor="model">
              模型名称
            </label>
            <Input
              id="model"
              type="text"
              placeholder={modelHint}
              value={model}
              onChange={(e) => {
                setModel(e.target.value);
                setErrors((prev) => ({ ...prev, model: undefined }));
                setProbe(null);
              }}
              aria-invalid={!!errors.model}
            />
            {errors.model && (
              <p className="text-destructive mt-1 text-xs" role="alert">
                {errors.model}
              </p>
            )}
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs font-medium"
              aria-expanded={showAdvanced}
            >
              <ChevronDown
                className={`size-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
                aria-hidden
              />
              高级：其他环节单独用另一个模型
            </button>
            {showAdvanced && (
              <div className="mt-2">
                <Input
                  type="text"
                  placeholder="留空则与上面的模型相同"
                  value={auxModel}
                  onChange={(e) => {
                    setAuxModel(e.target.value);
                    setProbe(null);
                  }}
                />
                <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                  此处的模型负责人设创建对话、状态评估、结局文案与长期记忆总结。这些调用均在角色回复
                  呈现之后于后台执行，耗时长短不影响你的实际体感，因此建议选用能力更强的旗舰模型，
                  不必顾虑速度。上面的模型负责角色回复，需等整段内容生成完毕才会显示，其响应速度
                  直接决定你的等待时长，建议优先考虑响应较快的型号。
                </p>
              </div>
            )}
          </div>

          <div className="border-border/60 bg-muted/40 rounded-xl border p-3">
            <div className="flex items-start gap-2">
              <Globe className="text-muted-foreground mt-0.5 size-3.5 shrink-0" aria-hidden />
              <p className="text-muted-foreground text-xs leading-relaxed">{WEB_SEARCH_NOTICE}</p>
            </div>
          </div>

          {probe && (
            <div
              role="status"
              className={`rounded-xl border p-3 text-xs leading-relaxed ${
                probe.ok
                  ? "border-primary/25 bg-primary/8 text-foreground"
                  : "border-destructive/30 bg-destructive/8 text-destructive"
              }`}
            >
              <p className="font-medium">{probe.ok ? "✅ " : "❌ "}{probe.message}</p>
              {probe.ok && probe.web_search_message && (
                <p className="text-muted-foreground mt-1.5">
                  {probe.web_search_supported ? "🌐 " : "○ "}
                  {probe.web_search_message}
                </p>
              )}
            </div>
          )}

          {saveError && (
            <div
              role="alert"
              className="border-destructive/30 bg-destructive/8 text-destructive rounded-xl border p-3 text-xs leading-relaxed"
            >
              {saveError}
            </div>
          )}

          {saved && (
            <div
              role="status"
              className="border-primary/25 bg-primary/8 text-foreground rounded-xl border p-3 text-xs"
            >
              ✅ 已保存
            </div>
          )}

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              disabled={busy}
              onClick={() => void handleTest()}
            >
              {testing ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden /> 测试中…
                </>
              ) : (
                "测试连接"
              )}
            </Button>
            <Button type="button" className="flex-1" disabled={busy} onClick={() => void handleSave()}>
              {saving ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden /> 保存中…
                </>
              ) : isSetup ? (
                "保存并开始"
              ) : (
                "保存"
              )}
            </Button>
          </div>
          <p className="text-muted-foreground text-center text-xs">
            保存时会自动验证，配置不可用会告诉你哪里填错了。
          </p>
        </div>
      </section>
    </div>
  );

  // setup 模式独占整屏：桌面端外壳（AppShell）把内容区锁成一屏高且 overflow-hidden，表单一旦
  // 超过一屏会被裁掉又滚不到。所以这里让根节点成为一个高度确定（h-full 撑满外壳给的一屏高）、
  // 可纵向滚动的块级容器；内层再用 flex + min-h-full 做垂直居中，兼顾「内容少时居中、内容多时
  // 能滚到底看到保存按钮」。用块级容器承载滚动而非直接在 flex 上滚，可避开 items-center 在内容
  // 超高时顶部被裁、滚不上去的老问题。
  if (isSetup) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="flex min-h-dvh items-center justify-center p-4">{content}</div>
      </div>
    );
  }

  // settings 模式下表单只是设置页的一部分，整页滚动交给外层 SettingsClient，这里只做水平居中。
  return <div className="flex justify-center p-4">{content}</div>;
}
