import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { AppComponent } from './app/app.component';
import { statusInterceptor } from './app/http-status.service';

bootstrapApplication(AppComponent, {
  providers: [
    provideHttpClient(withInterceptors([statusInterceptor])),
    provideAnimationsAsync()
  ]
});