import { createRouter, createWebHistory } from 'vue-router'

import StartPage from '../views/StartPage.vue'
import MRIVisualizer  from '../views/MRIVisualizer.vue'


const routes = [
    {path: '/', component: StartPage},
    {path: '/visualizer', component: MRIVisualizer}
]


export const router = createRouter(
    {
        history: createWebHistory(),
        routes
    }
)