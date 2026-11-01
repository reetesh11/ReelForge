import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { configureMonacoYaml } from "monaco-yaml";
import { useEffect } from "react";
import YamlWorker from "./yamlWorker?worker";

self.MonacoEnvironment = {
  getWorker(_id: string, label: string) {
    return label === "yaml" ? new YamlWorker() : new EditorWorker();
  },
};
loader.config({ monaco });

export default function MonacoYaml({
  value,
  onChange,
  readOnly,
  schema,
}: {
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  schema: Record<string, unknown> | undefined;
}) {
  useEffect(() => {
    if (!schema) return;
    const handle = configureMonacoYaml(monaco, {
      enableSchemaRequest: false,
      validate: true,
      hover: true,
      completion: true,
      schemas: [{ uri: "inmemory://reelforge/story.schema.json", fileMatch: ["*"], schema }],
    });
    return () => (handle as unknown as { dispose(): void }).dispose();
  }, [schema]);

  return (
    <div role="group" aria-label="YAML editor">
      <Editor
        height="28rem"
        language="yaml"
        path="story.yaml"
        value={value}
        theme="vs-dark"
        options={{ readOnly, minimap: { enabled: false }, scrollBeyondLastLine: false, tabSize: 2 }}
        onChange={(v) => onChange(v ?? "")}
      />
    </div>
  );
}
