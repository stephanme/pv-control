import { bootstrapApplication } from '@angular/platform-browser';
import { APP_INITIALIZER, provideExperimentalZonelessChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';

import { AppComponent } from './app/app.component';
import { statusInterceptor } from './app/http-status.service';
import { MatIconRegistry } from '@angular/material/icon';

bootstrapApplication(AppComponent, {
  providers: [
    provideExperimentalZonelessChangeDetection(),
    provideHttpClient(withInterceptors([statusInterceptor])),
    provideAnimationsAsync(),
    {
      provide: APP_INITIALIZER,
      multi: true,
      useFactory: (iconRegistry: MatIconRegistry) => () => {
        const defaultFontSetClasses = iconRegistry.getDefaultFontSetClass();
        const outlinedFontSetClasses = defaultFontSetClasses
          .filter((fontSetClass) => fontSetClass !== 'material-icons')
          .concat(['material-symbols-outlined']);
        iconRegistry.setDefaultFontSetClass(...outlinedFontSetClasses);
      },
      deps: [MatIconRegistry]
    }    
  ]
});