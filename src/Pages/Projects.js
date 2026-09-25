import React from "react";
import Project from "../Components/Project";
import { useContent } from "../ContentContext";

function Projects() {
  const { projectDetails, siteCopy } = useContent();
  return (
    <main className="container mx-auto max-width pt-10 mb-20">
      <section>
        <h1 className="text-2xl text-dark-heading dark:text-light-heading md:text-4xl xl:text-5xl xl:leading-tight font-bold">
          {siteCopy.projects_heading}
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-10">
          {React.Children.toArray(
            projectDetails.map(
              ({ id, title, image, description, techstack, previewLink, githubLink }) => (
                <Project
                  key={id}
                  title={title}
                  image={image}
                  description={description}
                  techstack={techstack}
                  previewLink={previewLink}
                  githubLink={githubLink}
                  labels={siteCopy}
                />
              )
            )
          )}
        </div>
      </section>
    </main>
  );
}

export default Projects;
