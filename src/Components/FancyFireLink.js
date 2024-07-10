import React from 'react';
import './css/FancyFireLink.css';

const FancyFireLink = ({ href, onClick, children }) => {
    return (
        <li>
            <a href={href} className="fancy-fire-link" onClick={onClick}>
                {children}
            </a>
        </li>
    );
};

export default FancyFireLink;
