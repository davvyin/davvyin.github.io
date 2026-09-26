import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Link } from "react-router-dom";
import VisitorAnalytics from "./VisitorAnalytics";

const originalFetch = global.fetch;
beforeEach(() => { global.fetch = jest.fn().mockResolvedValue({ status: 204 }); });
afterEach(() => { global.fetch = originalFetch; jest.restoreAllMocks(); });

function mount(path = "/?secret=ignored") {
  return render(<React.StrictMode><MemoryRouter initialEntries={[path]}>
    <VisitorAnalytics /><Link to="/projects?private=ignored#section">Projects</Link><Link to="/">Home</Link>
  </MemoryRouter></React.StrictMode>);
}

test("records initial and SPA page views once, strips queries, and counts return navigation", () => {
  mount();
  expect(global.fetch).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText("Projects"));
  fireEvent.click(screen.getByText("Home"));
  const events = global.fetch.mock.calls.map(([, options]) => JSON.parse(options.body));
  expect(events.map(event => event.path)).toEqual(["/", "/projects", "/"]);
  expect(new Set(events.map(event => event.event_id)).size).toBe(3);
  expect(global.fetch.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "same-origin" });
});

test("does not track private or unknown routes", () => {
  mount("/admin/camera/");
  expect(global.fetch).not.toHaveBeenCalled();
});

test("honors Do Not Track and Global Privacy Control", () => {
  Object.defineProperty(navigator, "doNotTrack", { configurable: true, value: "1" });
  const first = mount();
  expect(global.fetch).not.toHaveBeenCalled();
  first.unmount();
  Object.defineProperty(navigator, "doNotTrack", { configurable: true, value: undefined });
  Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: true });
  mount();
  expect(global.fetch).not.toHaveBeenCalled();
  Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: undefined });
});

test("sends only the initial referrer's origin and ignores network failures", () => {
  jest.spyOn(document, "referrer", "get").mockReturnValue("https://search.example/path?private=secret");
  global.fetch.mockRejectedValue(new Error("Offline"));
  mount();
  fireEvent.click(screen.getByText("Projects"));
  expect(JSON.parse(global.fetch.mock.calls[0][1].body).referrer).toBe("https://search.example");
  expect(JSON.parse(global.fetch.mock.calls[1][1].body).referrer).toBe("");
});
