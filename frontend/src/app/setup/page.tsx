import { SetupClient } from "@/components/setup/SetupClient";

export const metadata = { title: "配置大模型 - 心动实验室" };

export default function SetupPage() {
  return <SetupClient mode="setup" />;
}
