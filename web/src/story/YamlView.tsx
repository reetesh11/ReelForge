import { Suspense, lazy } from "react";

const MonacoYaml = lazy(() => import("./MonacoYaml"));

export function YamlView({
  text,
  onChange,
  errors,
  readOnly,
  schema,
}: {
  text: string;
  onChange: (value: string) => void;
  errors: string[];
  readOnly: boolean;
  schema: Record<string, unknown> | undefined;
}) {
  return (
    <div>
      {import.meta.env.MODE === "test" ? (
        <textarea
          className="yaml-editor"
          aria-label="YAML editor"
          spellCheck={false}
          value={text}
          readOnly={readOnly}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Suspense fallback={<p>Loading editor...</p>}>
          <MonacoYaml value={text} onChange={onChange} readOnly={readOnly} schema={schema} />
        </Suspense>
      )}
      {errors.length > 0 ? (
        <ul aria-label="YAML errors" className="errors">
          {errors.map((e, i) => (
            <li key={`${i}-${e}`}>{e}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
