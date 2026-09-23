import React from "react";
import { useContent } from "../ContentContext";

function Technologies() {
  const { technologies } = useContent();
  const renderGroup = (group) => technologies.filter((item) => item.group === group).map((item) => (
    <img key={item.id} src={item.image} title={item.name} alt={item.name} />
  ));
  return (
    <main className="container mx-auto max-width pt-10 pb-20 ">
      <section>
        <h1 className="text-2xl text-dark-heading dark:text-light-heading md:text-4xl xl:text-5xl xl:leading-tight font-bold">
          Tech Stack
        </h1>
        <p className="text-content py-2 lg:max-w-3xl">
          Technologies I've been working with recently
        </p>
      </section>
      <section className="grid grid-cols-4 md:grid-cols-5 lg:grid-cols-6 items-center gap-10 pt-6">
        {renderGroup("stack")}
      </section>
      <section>
        <h1 className="text-2xl pt-10 text-dark-heading dark:text-light-heading md:text-4xl xl:text-5xl xl:leading-tight font-bold">
          Tools
        </h1>
      </section>
      <section className="grid grid-cols-4 md:grid-cols-5 lg:grid-cols-6 items-center gap-10 pt-6">
        {renderGroup("tool")}
      </section>
    </main>
  );
}
export default Technologies;
