export default function ReaderAppearance({
  size,
  width,
  onSize,
  onWidth,
}: {
  size: number;
  width: string;
  onSize: (size: number) => void;
  onWidth: (width: string) => void;
}) {
  return (
    <div className="reader-appearance" data-keep-open>
      <h2>Reading appearance</h2>
      <div className="reader-setting-label">
        <span>Text size</span>
        <span>{size} px</span>
      </div>
      <div className="reader-segments" role="group" aria-label="Text size">
        {[14, 16, 18, 20, ...(size > 20 ? [size] : [])].map((value) => (
          <button
            key={value}
            aria-pressed={value === size}
            onClick={() => onSize(value)}
          >
            {value}
          </button>
        ))}
      </div>
      <div className="reader-setting-label">Reading width</div>
      <div className="reader-segments" role="group" aria-label="Reading width">
        <button
          aria-pressed={width === "comfortable"}
          onClick={() => onWidth("comfortable")}
        >
          Comfortable
        </button>
        <button aria-pressed={width === "wide"} onClick={() => onWidth("wide")}>
          Wide
        </button>
      </div>
      <p>Changes the article; menus stay compact.</p>
    </div>
  );
}
