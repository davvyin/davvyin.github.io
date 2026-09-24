import React from "react";
import { act, render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "./App";

jest.mock("gsap", () => ({
  timeline: () => { const timeline = { from: () => timeline, kill: jest.fn() }; return timeline; },
  set: jest.fn(),
}));
const content = {
  personalDetails: { name: "Test owner", img: "/photo.jpg", about: "Biography from admin" },
  logos: { logogradient: "/logo.png" }, contactDetails: { email: "test@example.com" },
  socialMediaUrl: {}, codingChallengesUrl: "https://example.com/challenges", footerText: "Test footer",
  siteCopy: {
    home_greeting: "Hello", home_name_leadin: "I'm", about_heading: "About me",
    experience_heading: "Experience", education_heading: "Education",
    projects_heading: "My work", contact_heading: "Contact me",
    technologies_heading: "Tech stack", technologies_intro: "Recent tools",
    tools_heading: "Tools", nav_home: "Home", nav_about: "Bio",
    nav_technologies: "Stack", nav_projects: "Work", nav_contact: "Say hello",
    coding_challenges_label: "Coding challenges", project_keywords_label: "Keywords",
    project_preview_label: "Live Preview", project_code_label: "View Code", footer_admin_label: "Admin",
  },
  workDetails: [{ Position: "Engineer", Company: "Example" }], eduDetails: [],
  projectDetails: [{ id: 1, title: "Admin project", description: "Saved description", githubLink: "https://example.com/code" }],
  technologies: [{ id: 1, name: "Python", group: "stack", image: "/python.svg" }],
};
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test("existing pages render API content and navigation retains the admin entry", async () => {
  window.history.replaceState({}, "", "/");
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => content });
  await act(async () => { render(<App />); });
  expect(await screen.findByRole("heading", { name: "Test owner" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Test owner" })).toHaveAttribute("src", "/photo.jpg");
  expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin/");
  fireEvent.click(screen.getByRole("link", { name: "Bio" }));
  expect(screen.getByRole("heading", { name: "About me" })).toBeInTheDocument();
  expect(await screen.findByText("Biography from admin")).toBeInTheDocument();
  expect(screen.getByText("Engineer")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "Work" }));
  expect(screen.getByRole("heading", { name: "My work" })).toBeInTheDocument();
  expect(await screen.findByText("Admin project")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View Code" })).toHaveAttribute("href", "https://example.com/code");
  fireEvent.click(screen.getByRole("link", { name: "Stack" }));
  expect(await screen.findByRole("img", { name: "Python" })).toHaveAttribute("src", "/python.svg");
  fireEvent.click(screen.getByRole("link", { name: "Say hello" }));
  expect(screen.getByRole("heading", { name: "Contact me" })).toBeInTheDocument();
  expect(await screen.findByText("test@example.com")).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledTimes(1);
});
