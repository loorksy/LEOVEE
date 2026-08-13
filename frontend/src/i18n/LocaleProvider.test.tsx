import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { LocaleProvider } from "./LocaleProvider";
import { useLocale } from "./context";

function Probe() {
  const { t, locale, dir, setLocale } = useLocale();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="dir">{dir}</span>
      <span data-testid="label">{t("direction.buy")}</span>
      <button onClick={() => setLocale("en")}>switch</button>
    </div>
  );
}

describe("LocaleProvider", () => {
  it("renders Arabic and RTL by default", () => {
    render(
      <LocaleProvider initialLocale="ar">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("locale")).toHaveTextContent("ar");
    expect(screen.getByTestId("dir")).toHaveTextContent("rtl");
    expect(screen.getByTestId("label")).toHaveTextContent("شراء");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("switches locale and document direction together", async () => {
    render(
      <LocaleProvider initialLocale="ar">
        <Probe />
      </LocaleProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("label")).toHaveTextContent("Buy");
    expect(screen.getByTestId("dir")).toHaveTextContent("ltr");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("refuses to render outside the provider", () => {
    // Silently defaulting would leave the document direction wrong, which is
    // easy to miss in review and hard to trace afterwards.
    expect(() => render(<Probe />)).toThrow(/inside <LocaleProvider>/);
  });
});
