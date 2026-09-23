import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ContentProvider, useContent } from "./ContentContext";
import Projects from "./Pages/Projects";

const content = {
  personalDetails: { name: "Admin edited name" }, logos: {}, contactDetails: {},
  socialMediaUrl: {}, footerText: "Footer", workDetails: [], eduDetails: [],
  projectDetails: [], technologies: [],
};
const originalFetch = global.fetch;
beforeEach(() => { global.fetch = jest.fn(); });
afterEach(() => { global.fetch = originalFetch; });
function Name() { return <h1>{useContent().personalDetails.name}</h1>; }

test("loads and displays database content", async () => {
  global.fetch.mockResolvedValue({ ok: true, json: async () => content });
  render(<ContentProvider><Name /></ContentProvider>);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByRole("heading")).toHaveTextContent("Admin edited name");
  expect(global.fetch).toHaveBeenCalledWith("/api/content/", expect.objectContaining({signal: expect.anything()}));
});

test("shows a retry action on failure and recovers", async () => {
  global.fetch.mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValueOnce({ ok: true, json: async () => content });
  render(<ContentProvider><Name /></ContentProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("could not load");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("heading")).toHaveTextContent("Admin edited name");
});

test.each([
  { ok: false, json: async () => content },
  { ok: true, json: async () => ({}) },
])("rejects unsuccessful or invalid responses", async (response) => {
  global.fetch.mockResolvedValue(response);
  render(<ContentProvider><Name /></ContentProvider>);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText("Admin edited name")).not.toBeInTheDocument();
});

test("empty project collections do not restore hardcoded projects", async () => {
  global.fetch.mockResolvedValue({ ok: true, json: async () => content });
  const { container } = render(<ContentProvider><Projects /></ContentProvider>);
  await screen.findByRole("heading", { name: "Selected Projects" });
  expect(container.querySelectorAll("article")).toHaveLength(0);
  expect(screen.queryByText("LingoLeap")).not.toBeInTheDocument();
});

test("aborts requests when unmounted", async () => {
  global.fetch.mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<ContentProvider><Name /></ContentProvider>);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  const signal = global.fetch.mock.calls[0][1].signal;
  unmount();
  expect(signal.aborted).toBe(true);
});
