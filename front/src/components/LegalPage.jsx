const TERMS_SECTIONS = [
  { title: "1. 服务说明", body: "DevMind AI 为企业内部技术知识工作空间，提供知识库管理、智能问答与检索等服务。使用本服务即表示你已阅读并同意本协议。" },
  { title: "2. 账号与安全", body: "你应使用真实、合法的信息注册账号，并妥善保管登录凭证。因账号保管不当导致的损失由你自行承担。" },
  { title: "3. 使用规范", body: "不得利用本服务上传违法、侵权或恶意内容，不得尝试未授权访问系统、数据或其他用户资源。" },
  { title: "4. 知识产权", body: "你上传至知识库的内容，其知识产权仍归你或原权利人所有；你授权平台在提供服务所必需的范围内存储、索引与展示。" },
  { title: "5. 服务变更", body: "我们可能根据业务需要更新功能或本协议，更新后继续使用服务即视为接受变更。" },
];

const PRIVACY_SECTIONS = [
  { title: "1. 信息收集", body: "我们会收集你注册时提供的用户名、手机号等信息，以及使用服务过程中产生的操作日志，用于账号认证、安全审计与服务改进。" },
  { title: "2. 信息使用", body: "收集的信息仅用于提供与优化 DevMind AI 服务，不会用于与本服务无关的营销目的。" },
  { title: "3. 信息存储与保护", body: "数据存储于企业授权的服务环境中，我们采取合理的访问控制与加密措施保护数据安全。" },
  { title: "4. 信息共享", body: "除法律法规要求或获得你明确授权外，我们不会向第三方出售或披露你的个人信息。" },
  { title: "5. 你的权利", body: "你可联系管理员查询、更正或删除与你相关的账号信息，法律法规另有规定的除外。" },
];

export default function LegalPage({ type = "terms", onBack }) {
  const isTerms = type === "terms";
  const sections = isTerms ? TERMS_SECTIONS : PRIVACY_SECTIONS;

  return (
    <main className="legal-page">
      <article className="legal-box">
        <button type="button" className="legal-back" onClick={onBack}>← 返回</button>
        <h1>{isTerms ? "用户协议" : "隐私政策"}</h1>
        <p className="legal-updated">最近更新：2026-08-23</p>
        <div className="legal-content">
          {sections.map((section) => (
            <section key={section.title}>
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </section>
          ))}
        </div>
      </article>
    </main>
  );
}
