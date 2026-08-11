import { afterEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import { RequireAuth } from "./RequireAuth";
import { clearTokens, setTokens } from "@/api/authStore";

function ProtectedPage() {
  return <p>secret content</p>;
}

function LoginStub() {
  return <p>login page</p>;
}

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={["/memory"]}>
      <Routes>
        <Route path="/login" element={<LoginStub />} />
        <Route element={<RequireAuth />}>
          <Route path="/memory" element={<ProtectedPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  afterEach(() => {
    clearTokens();
  });

  it("redirects to /login when unauthenticated", () => {
    renderGuarded();
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders the protected route when authenticated", () => {
    setTokens({ access_token: "tok", refresh_token: "r" });
    renderGuarded();
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });
});
