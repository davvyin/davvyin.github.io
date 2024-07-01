// Enter all your detials in this file
// Logo images
import logogradient from "./assets/favicon/android-chrome-192x192.png";
// import logo from "./assets/logo2.svg";
// Profile Image
import profile from "./assets/profile.jpg";
// Tech stack images
import html from "./assets/techstack/html.png";
import css from "./assets/techstack/css.png";
import sass from "./assets/techstack/sass.png";
import js from "./assets/techstack/js.png";
import react from "./assets/techstack/react.png";
import redux from "./assets/techstack/redux.png";
import tailwind from "./assets/techstack/tailwind.png";
import bootstrap from "./assets/techstack/bootstrap.png";
import vscode from "./assets/techstack/vscode.png";
import github from "./assets/techstack/github.png";
import git from "./assets/techstack/git.png";
import npm from "./assets/techstack/npm.png";
import postman from "./assets/techstack/postman.png";
import figma from "./assets/techstack/figma.png";
// Porject Images
import projectImage1 from "./assets/projects/project1.jpg";
import Boston_University from "./assets/projects/Boston_University.png";
import sc from "./assets/projects/sc.png";
import projectImage4 from "./assets/projects/project4.jpg";
import projectImage5 from "./assets/projects/project5.jpg";
import projectImage6 from "./assets/projects/project6.jpg";

// Logos
export const logos = {
  logogradient: logogradient,
  logo: logogradient,
};

// Enter your Personal Details here
export const personalDetails = {
  name: "Dawei (David) Yin",
  tagline: "",
  img: profile,
  about: `A Computer Science grad student at Columbia University. Passionate about tech innovations, I've honed my skills in Software Development, Data Analysis and visualization. Seeking opportunities in forward-thinking tech companies to apply my expertise.`
};

// Enter your Social Media URLs here
export const socialMediaUrl = {
  linkdein: "https://www.linkedin.com/in/davyin/",
  github: "https://github.com/davvyin",
  instagram: "https://www.instagram.com/",
};

// // Enter your Work Experience here
// export const workDetails = [
//   {
//     Position: "SRE Internship",
//     Company: `Tencent America`,
//     Location: "Los Angeles",
//     Type: "Full Time",
//     Duration: "Jun 2024 - Aug 2024",
//   },
//   {
//     Position: "Full Stack Engineer",
//     Company: `LingoLeap`,
//     Location: "Santa Clara, Remote",
//     Type: "Part Time",
//     Duration: "May 2023 - Jan 2023",
//   },
//   {
//     Position: "Research Assi",
//     Company: `HI-Lab, Boston University`,
//     Location: "Bengaluru",
//     Type: "Internship",
//     Duration: "Sep 2021 - Dec 2021",
//   },
// ];

// // Enter your Education Details here
// export const eduDetails = [
//   {
//     Position: "Frontend Development",
//     Company: "Udemy, YouTube, Google, Medium",
//     Location: "Online",
//     Type: "Full Time",
//     Duration: "Jan 2022 - Present",
//   },
//   {
//     Position: "Bachelor in Electronics & Communication",
//     Company: `Your College Name here`,
//     Location: "Bengaluru",
//     Type: "Full Time",
//     Duration: "Aug 2020 - Present",
//   },
// ];
// Enter your Work Experience here
export const workDetails = [
  {
    Position: "Site Reliability Engineer Internship",
    Company: `Tencent America`,
    Location: "Los Angeles, CA",
    Type: "Full Time",
    Duration: "Jun 2024 - Aug 2024",
  },
  {
    Position: "Full Stack Engineer",
    Company: `LingoLeap`,
    Location: "Santa Clara, Remote",
    Type: "Part Time",
    Duration: "May 2023 - Jan 2024",
  },
  {
    Position: "Research Assistant",
    Company: `HI-Lab, Boston University`,
    Location: "Boston, MA",
    Type: "Internship",
    Duration: "Jan 2022 - Jun 2023",
  },
  {
    Position: "Software Engineer Intern",
    Company: `Tencent America, Security Department`,
    Location: "Palo Alto, CA",
    Type: "Internship",
    Duration: "Jun 2022 - Aug 2022",
  },
];
export const eduDetails = [
  {
    Position: "M.S. in Computer Science",
    Company: "Columbia University",
    Location: "New York, NY",
    Type: "Full Time",
    Duration: "Expected Dec 2024",
  },
  {
    Position: "M.S. in Data Analytics",
    Company: "Boston University",
    Location: "Boston, MA",
    Type: "Full Time",
    Duration: "May 2023",
  },
  {
    Position: "B.A. in Computer Science & Mathematics",
    Company: "Boston University",
    Location: "Boston, MA",
    Type: "Full Time",
    Duration: "May 2021",
  },
];


// Tech Stack and Tools
export const techStackDetails = {
  html: html,
  css: css,
  js: js,
  react: react,
  redux: redux,
  sass: sass,
  tailwind: tailwind,
  bootstrap: bootstrap,
  vscode: vscode,
  postman: postman,
  npm: npm,
  git: git,
  github: github,
  figma: figma,
};

// Enter your Project Details here
export const projectDetails = [
  {
    title: "LingoLeap",
    image: projectImage1,
    description: `Your Personal AI Tutor for Language Learning`,
    techstack: false,
    previewLink: "https://lingoleap.ai/",
    githubLink: false,
  },
  {
    title: "Participant Allocation Manager",
    image: Boston_University,
    description: `PAM streamlines the participant enrollment process and participant allocation, supported by commonly used allocation algorithms including simple randomization, permuted block randomization, stratified block randomization, and adaptive minimization.`,
    techstack: "Algorithm, Chatbot, Python, Flask, React",
    previewLink: "https://documenter.getpostman.com/view/20352268/2s8YRcNbte#8f1053fe-6a4d-4c33-a8dd-8156aa6a03d1",
    githubLink: "https://github.com/dataperformance/PAM",
  },
  {
    title: "Hython",
    image: false,
    description: `Hython is an imperative language that resembles a high-level language like Python.`,
    techstack: "Ocaml, Complier, LLVM",
    previewLink: false,
    githubLink: "https://github.com/Dwyin7/4115_Hython",
  },
  {
    title: "Sweety Course",
    image: sc,
    description: `Course infomation system.`,
    techstack: "Cloud, Docker, Microservices, Algorithm",
    // previewLink: "https://google.com",
    githubLink: "https://github.com/HEXA-QUAD",
  },
    {
      title: "Paxos model checking",
      // image: projectImage5,
      description: `Distributed system algorithm paxos model checker`,
      techstack: "Distributed system, Model checker, Golang",
      // previewLink: "https://google.com",
      githubLink: "https://github.com/davvyin/paxos-model-checking/tree/main",
    },
  //   {
  //     title: "Project title 6",
  //     image: projectImage6,
  //     description: `This is sample project description random things are here in description This is sample
  // project lorem ipsum generator for dummy content`,
  //     techstack: "HTML/CSS, JavaScript",
  //     previewLink: "https://google.com",
  //     githubLink: "https://github.com",
  //   },
];

// Enter your Contact Details here
export const contactDetails = {
  email: "dawei.yin at columbia dot edu",
};
